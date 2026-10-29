//! Follow credential-free API discovery, provider discovery and key-set validation.

use std::time::Duration;

use inframeld_sdk::HttpClient;
use openidconnect::IssuerUrl;

use super::{
    BODY_LIMIT, DiscoveredInstallation, DiscoveryError, DiscoveryOptions,
    DiscoveryProviderMetadata, ManagedLocalContext,
    error::sdk_error,
    installation::{validate_binding, validate_provider_profile},
    oidc_transport::{OidcTransport, client},
    url_policy::UrlPolicy,
};

/// Apply the fixed budgets with an optional, independently trusted local context.
pub(crate) async fn discover_with_context(
    api_identity: &str,
    options: DiscoveryOptions,
    managed: Option<&ManagedLocalContext>,
) -> Result<DiscoveredInstallation, DiscoveryError> {
    discover_with_budget(
        api_identity,
        options,
        managed,
        Duration::from_secs(10),
        Duration::from_secs(5),
    )
    .await
}

/// Bound the entire sequence, with short budgets available to controlled unit tests.
pub(super) async fn discover_with_budget(
    api_identity: &str,
    options: DiscoveryOptions,
    managed: Option<&ManagedLocalContext>,
    total_budget: Duration,
    request_budget: Duration,
) -> Result<DiscoveredInstallation, DiscoveryError> {
    tokio::time::timeout(
        total_budget,
        discover_inner(api_identity, options, managed, request_budget),
    )
    .await
    .map_err(|_| DiscoveryError::Timeout)?
}

/// Read API metadata before admitting provider work, preserving validation order.
async fn discover_inner(
    api_identity: &str,
    options: DiscoveryOptions,
    managed: Option<&ManagedLocalContext>,
    request_budget: Duration,
) -> Result<DiscoveredInstallation, DiscoveryError> {
    let policy = UrlPolicy::new(managed);
    let api = policy.api_url(api_identity)?;
    if managed.is_some() && options.proxy.is_some() {
        return Err(DiscoveryError::UnsupportedProfile);
    }
    let transport = client(options, request_budget)?;
    let sdk = HttpClient::with_client(transport.clone())
        .with_base_url(api.origin().ascii_serialization())
        .with_max_response_body_bytes(BODY_LIMIT);
    let path = api.path().strip_prefix('/').unwrap_or(api.path());
    let metadata = if path.is_empty() {
        sdk.get_protected_resource_metadata()
            .await
            .map_err(sdk_error)?
            .body
    } else {
        sdk.get_protected_resource_metadata_for_path(path)
            .await
            .map_err(sdk_error)?
            .body
    };
    validate_binding(&metadata, api_identity, managed)?;
    let issuer = &metadata.authorization_servers.0;
    let issuer_url = policy.issuer_url(issuer)?;
    let origin = issuer_url.origin();
    let http = OidcTransport::new(transport, origin.clone(), policy.clone());
    let provider = DiscoveryProviderMetadata::discover_async(
        IssuerUrl::new(issuer.to_owned()).map_err(|_| DiscoveryError::InvalidUrl)?,
        &http,
    )
    .await
    .map_err(|error| match error {
        openidconnect::DiscoveryError::Request(error) => error,
        openidconnect::DiscoveryError::Validation(_) => DiscoveryError::IdentityMismatch,
        _ => DiscoveryError::InvalidMetadata,
    })?;
    if provider.issuer().as_str() != issuer {
        return Err(DiscoveryError::IdentityMismatch);
    }
    validate_provider_profile(&provider, &origin, &policy)?;
    Ok(DiscoveredInstallation {
        resource: metadata.resource,
        installation_id: metadata.inframeld.installation_id,
        client_id: "inframeld-cli",
        provider,
    })
}
