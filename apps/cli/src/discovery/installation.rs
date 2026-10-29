//! Represent the public discovery profile and validate its required bindings.

use std::fmt;

use inframeld_sdk::types::ProtectedResourceMetadataResponse;
use url::Url;
use uuid::Uuid;

use super::{DiscoveryError, ManagedLocalContext, url_policy::UrlPolicy};

use openidconnect::{
    AdditionalProviderMetadata, ProviderMetadata,
    core::{
        CoreAuthDisplay, CoreClaimName, CoreClaimType, CoreClientAuthMethod, CoreGrantType,
        CoreJsonWebKey, CoreJweContentEncryptionAlgorithm, CoreJweKeyManagementAlgorithm,
        CoreResponseMode, CoreResponseType, CoreSubjectIdentifierType,
    },
};

/// Required first-party extensions to standard provider metadata.
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ProviderExtensions {
    /// Supported PKCE transforms. This profile requires S256.
    #[serde(default)]
    pub code_challenge_methods_supported: Vec<String>,
    /// Public selected-login revocation endpoint, when advertised.
    pub revocation_endpoint: Option<Url>,
}
impl AdditionalProviderMetadata for ProviderExtensions {}

/// Standard OIDC metadata with the explicitly checked first-party extensions.
pub type DiscoveryProviderMetadata = ProviderMetadata<
    ProviderExtensions,
    CoreAuthDisplay,
    CoreClientAuthMethod,
    CoreClaimName,
    CoreClaimType,
    CoreGrantType,
    CoreJweContentEncryptionAlgorithm,
    CoreJweKeyManagementAlgorithm,
    CoreJsonWebKey,
    CoreResponseMode,
    CoreResponseType,
    CoreSubjectIdentifierType,
>;

/// Explicit trusted transport configuration, never saved login credentials.
#[derive(Default)]
pub struct DiscoveryOptions {
    /// Additional CA certificates for private installations.
    pub certificate_authorities: Vec<reqwest::Certificate>,
    /// An operator-selected proxy. Environment proxies are not used implicitly.
    pub proxy: Option<reqwest::Proxy>,
}

impl fmt::Debug for DiscoveryOptions {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("DiscoveryOptions")
            .field(
                "certificate_authorities",
                &self.certificate_authorities.len(),
            )
            .field("proxy_configured", &self.proxy.is_some())
            .finish()
    }
}

/// Validated public facts for a future explicit target registration.
#[derive(Debug)]
pub struct DiscoveredInstallation {
    /// Exact API resource identity and token audience.
    pub resource: String,
    /// Stable installation identity across ordinary restart.
    pub installation_id: Uuid,
    /// The fixed first-party client.
    pub client_id: &'static str,
    /// Validated issuer metadata, including its bounded, verified key set.
    pub provider: DiscoveryProviderMetadata,
}

/// Require exact API/installation binding before accepting profile capabilities.
pub(super) fn validate_binding(
    metadata: &ProtectedResourceMetadataResponse,
    expected: &str,
    managed: Option<&ManagedLocalContext>,
) -> Result<(), DiscoveryError> {
    if metadata.resource != expected
        || managed
            .is_some_and(|context| metadata.inframeld.installation_id != context.installation_id)
    {
        return Err(DiscoveryError::IdentityMismatch);
    }
    if metadata.inframeld.schema_version != 1
        || metadata.inframeld.client_id.as_str() != "inframeld-cli"
    {
        return Err(DiscoveryError::UnsupportedProfile);
    }
    Ok(())
}

/// Check endpoint destinations and the fixed public-client login capabilities.
pub(super) fn validate_provider_profile(
    provider: &DiscoveryProviderMetadata,
    origin: &url::Origin,
    policy: &UrlPolicy,
) -> Result<(), DiscoveryError> {
    let mut endpoints = vec![
        provider.authorization_endpoint().url(),
        provider.jwks_uri().url(),
    ];
    let token = provider
        .token_endpoint()
        .ok_or(DiscoveryError::InvalidMetadata)?;
    endpoints.push(token.url());
    if let Some(endpoint) = provider.userinfo_endpoint() {
        endpoints.push(endpoint.url());
    }
    if let Some(endpoint) = &provider.additional_metadata().revocation_endpoint {
        endpoints.push(endpoint);
    }
    for endpoint in endpoints {
        if endpoint.origin() != *origin {
            return Err(DiscoveryError::IdentityMismatch);
        }
        policy.provider_url(endpoint.as_str())?;
    }
    let default_grants = [CoreGrantType::AuthorizationCode, CoreGrantType::Implicit];
    let grants = provider
        .grant_types_supported()
        .map_or(default_grants.as_slice(), Vec::as_slice);
    if !grants.contains(&CoreGrantType::AuthorizationCode)
        || !grants.contains(&CoreGrantType::RefreshToken)
        || !provider
            .response_types_supported()
            .iter()
            .any(|types| types.as_slice() == [CoreResponseType::Code])
        || !provider
            .token_endpoint_auth_methods_supported()
            .as_ref()
            .is_some_and(|methods| methods.contains(&CoreClientAuthMethod::None))
    {
        return Err(DiscoveryError::UnsupportedProfile);
    }
    if !provider
        .additional_metadata()
        .code_challenge_methods_supported
        .iter()
        .any(|method| method == "S256")
    {
        return Err(DiscoveryError::UnsupportedProfile);
    }
    Ok(())
}
