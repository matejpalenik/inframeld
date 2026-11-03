//! Coordinate fresh human proof without saving a login or changing its trusted binding.

use std::{future::Future, pin::Pin, time::Duration};

use openidconnect::{
    AccessTokenHash, AuthenticationFlow, ClientId, CsrfToken, EndpointMaybeSet, EndpointNotSet,
    EndpointSet, Nonce, OAuth2TokenResponse, PkceCodeChallenge, RedirectUrl, RevocationUrl, Scope,
    TokenResponse,
    core::{CoreClient, CoreResponseType, CoreRevocableToken, CoreTokenResponse, CoreTokenType},
};
use zeroize::Zeroizing;

use serde::Serialize;
use tokio::time::Instant;
use url::Url;
use uuid::Uuid;

use crate::discovery::{DiscoveryOptions, discover};

use super::{
    callback::{CallbackListener, CallbackResponse},
    recipient_proof::{RecipientProof, RepairRequest},
    transport::AuthTransport,
};

use super::maintenance_handoff::{CleanupStatus, ExecutionSpec, HandoffOutcome};

/// Independently trusted installation and recipient intent, frozen for one operation.
pub struct HostContext {
    api: String,
    issuer: String,
    client_id: String,
    installation_id: Uuid,
    identity_id: Uuid,
    options: DiscoveryOptions,
}

/// Invalid trusted setup input never becomes provider or SDK configuration.
#[derive(Debug, Clone, Copy, thiserror::Error)]
#[error("The trusted host context is invalid or unsupported.")]
pub struct InvalidHostContext;

#[derive(serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct HostConfiguration {
    schema_version: u8,
    api: String,
    issuer: String,
    client_id: String,
    installation_id: Uuid,
    expected_identity_id: Uuid,
    #[serde(default)]
    certificate_authorities: Vec<String>,
    proxy: Option<String>,
}

impl HostContext {
    /// Parse one strict host-controlled context, including explicit public CA PEMs.
    ///
    /// # Errors
    /// Rejects unknown/duplicate fields, malformed values and unsupported setup.
    pub fn parse(bytes: &[u8]) -> Result<Self, InvalidHostContext> {
        if bytes.len() > 65_536 {
            return Err(InvalidHostContext);
        }
        let configuration: HostConfiguration =
            serde_json::from_slice(bytes).map_err(|_| InvalidHostContext)?;
        if configuration.schema_version != 1
            || configuration.client_id != "inframeld-cli"
            || configuration.api.len() > 8192
            || configuration.issuer.len() > 8192
            || configuration.certificate_authorities.len() > 16
        {
            return Err(InvalidHostContext);
        }
        let mut certificates = Vec::new();
        for pem in configuration.certificate_authorities {
            let bundle = reqwest::Certificate::from_pem_bundle(pem.as_bytes())
                .map_err(|_| InvalidHostContext)?;
            if bundle.is_empty() {
                return Err(InvalidHostContext);
            }
            certificates.extend(bundle);
        }
        let proxy = configuration
            .proxy
            .map(reqwest::Proxy::all)
            .transpose()
            .map_err(|_| InvalidHostContext)?;
        Ok(Self::new(
            configuration.api,
            configuration.issuer,
            configuration.client_id,
            configuration.installation_id,
            configuration.expected_identity_id,
            DiscoveryOptions {
                certificate_authorities: certificates,
                proxy,
            },
        ))
    }

    /// Capture host facts without discovery, credential lookup or ambient configuration.
    #[must_use]
    pub fn new(
        api: String,
        issuer: String,
        client_id: String,
        installation_id: Uuid,
        identity_id: Uuid,
        options: DiscoveryOptions,
    ) -> Self {
        Self {
            api,
            issuer,
            client_id,
            installation_id,
            identity_id,
            options,
        }
    }
}

impl std::fmt::Debug for HostContext {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("HostContext([frozen trusted binding])")
    }
}

/// Flow-sensitive browser navigation data, never a log or ordinary output payload.
pub struct AuthorizationReady {
    /// Navigate only this maintained-library-generated authorization URL.
    pub authorization_url: Url,
    /// The exact trusted issuer, including its original spelling.
    pub issuer: String,
    /// The complete URI also retained for code exchange.
    pub callback_uri: String,
}

impl std::fmt::Debug for AuthorizationReady {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("AuthorizationReady([flow-sensitive navigation])")
    }
}

/// Browser dispatch failed without exposing a URL or arbitrary OS diagnostic.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BrowserFailureKind {
    /// Dispatch failed before a usable browser handoff.
    Failed,
    /// The caller cancelled dispatch.
    Cancelled,
    /// The original or adapter deadline expired.
    TimedOut,
}

/// Safe dispatch failure and its independently observed resource cleanup.
#[derive(Debug, Clone, Copy, thiserror::Error)]
#[error("The private browser handoff did not complete ({kind:?}).")]
pub struct BrowserLaunchError {
    /// Fixed safe failure classification.
    pub kind: BrowserFailureKind,
    /// Owned socket or launcher cleanup, separate from browser rollback.
    pub resource_cleanup: CleanupStatus,
}
impl BrowserLaunchError {
    /// Classify a failure that created no retained cleanup obligation.
    #[must_use]
    pub fn failed() -> Self {
        Self {
            kind: BrowserFailureKind::Failed,
            resource_cleanup: CleanupStatus::NotNeeded,
        }
    }
}

/// Dispatch browser navigation without taking over OAuth or returning claims.
pub trait BrowserLauncher: Send {
    /// Return after navigation dispatch, using only the original operation deadline.
    fn open(
        &mut self,
        ready: &AuthorizationReady,
        deadline: Instant,
        cancellation: Pin<&mut (dyn Future<Output = ()> + Send)>,
    ) -> impl Future<Output = Result<(), BrowserLaunchError>> + Send;
}

/// Safe stage classifications retain no upstream response or credential text.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum FailureKind {
    /// The exact proof-free repair request was invalid.
    InvalidRequest,
    /// Trusted host context or transport configuration was invalid.
    InvalidContext,
    /// Anonymous discovery did not complete.
    Discovery,
    /// Discovery or recipient identity disagreed with the frozen binding.
    Binding,
    /// Browser dispatch did not complete.
    Browser,
    /// A correctly associated authorization response denied access.
    Denied,
    /// No valid callback was acquired.
    Callback,
    /// The one code exchange failed or was uncertain.
    Exchange,
    /// Maintained ID-token validation or its explicit binding checks failed.
    Identity,
    /// The generated session operation did not verify an admitted human.
    Session,
    /// The transient-only request unexpectedly created renewable credentials.
    UnexpectedRefresh,
    /// The caller cancelled the operation.
    Cancelled,
    /// The original interaction deadline expired.
    TimedOut,
}

/// A failure keeps credential cleanup uncertainty separate from its stage.
#[derive(Debug, Serialize, thiserror::Error)]
#[serde(rename_all = "camelCase")]
#[error("Transient recipient proof failed ({kind:?}).")]
pub struct RepairFailure {
    /// Fixed safe stage classification.
    pub kind: FailureKind,
    /// Cleanup of a failed browser dispatch when that boundary was reached.
    pub resource_cleanup: CleanupStatus,
    /// Newly issued credentials may need independent operator cleanup.
    pub credential_cleanup: CleanupStatus,
}

/// Report original maintenance facts and transient credential cleanup independently.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RepairOutcome {
    /// Receipt evidence and protected child cleanup observations.
    pub maintenance: HandoffOutcome,
    /// Standard public revocation of only the newly issued credential set.
    pub credential_cleanup: CleanupStatus,
}

/// Acquire fresh proof for one already-admitted recipient and submit repair once.
///
/// Validates proof-free input before effects. This does not bootstrap admission,
/// save credentials, refresh, log out a saved account or select a stored target.
///
/// # Errors
/// Returns safe stage and cleanup facts without token or provider diagnostics.
pub async fn repair(
    host: &HostContext,
    request: &[u8],
    execution: &ExecutionSpec,
    browser: &mut impl BrowserLauncher,
    cancellation: impl Future<Output = ()> + Send,
) -> Result<RepairOutcome, RepairFailure> {
    // Capture exactly once, before validation can admit any external effect.
    let deadline = Instant::now() + Duration::from_mins(10);
    let request = host.bound_request(request)?;
    let mut cancellation = std::pin::pin!(cancellation);
    let PendingAuthorization {
        transport,
        oidc,
        callback,
        require_issuer,
        state,
        nonce,
        verifier,
        ready,
    } = prepare_authorization(host, deadline, cancellation.as_mut()).await?;
    // The adapter observes cancellation and awaits its owned finalizer. Dropping
    // a process-launch future here would not establish reaping or cleanup.
    browser
        .open(&ready, deadline, cancellation.as_mut())
        .await
        .map_err(|error| RepairFailure {
            kind: match error.kind {
                BrowserFailureKind::Failed => FailureKind::Browser,
                BrowserFailureKind::Cancelled => FailureKind::Cancelled,
                BrowserFailureKind::TimedOut => FailureKind::TimedOut,
            },
            credential_cleanup: CleanupStatus::NotNeeded,
            resource_cleanup: error.resource_cleanup,
        })?;
    let response = within(
        deadline,
        cancellation.as_mut(),
        callback.receive(state, require_issuer, deadline),
    )
    .await
    .map_err(|kind| failure(kind, CleanupStatus::NotNeeded))?
    .map_err(|_| failure(FailureKind::Callback, CleanupStatus::NotNeeded))?;
    let code = match response {
        CallbackResponse::Code(code) => code,
        CallbackResponse::Denied => {
            return Err(failure(FailureKind::Denied, CleanupStatus::NotNeeded));
        }
    };
    let exchange = oidc
        .exchange_code(code)
        .map_err(|_| failure(FailureKind::InvalidContext, CleanupStatus::NotNeeded))?
        .set_pkce_verifier(verifier);
    let tokens = within(
        deadline,
        cancellation.as_mut(),
        exchange.request_async(&transport),
    )
    .await
    .map_err(|kind| failure(kind, CleanupStatus::Unconfirmed))?
    .map_err(|_| failure(FailureKind::Exchange, CleanupStatus::Unconfirmed))?;
    if tokens.refresh_token().is_some() {
        let cleanup = revoke_new(&oidc, &transport, &tokens).await;
        return Err(failure(FailureKind::UnexpectedRefresh, cleanup));
    }
    if validate_identity(&oidc, &tokens, &nonce, host).is_err() {
        let cleanup = revoke_new(&oidc, &transport, &tokens).await;
        return Err(failure(FailureKind::Identity, cleanup));
    }
    let principal = match within(
        deadline,
        cancellation.as_mut(),
        transport.session_principal(tokens.access_token()),
    )
    .await
    {
        Ok(Ok(principal)) => principal,
        result => {
            let kind = match result {
                Err(kind) => kind,
                _ => FailureKind::Session,
            };
            let cleanup = revoke_new(&oidc, &transport, &tokens).await;
            return Err(failure(kind, cleanup));
        }
    };
    let proof = RecipientProof {
        access_token: Zeroizing::new(tokens.access_token().secret().clone()),
        installation_id: host.installation_id,
        identity_id: host.identity_id,
        principal_id: principal,
    };
    let maintenance = super::maintenance_handoff::handoff(
        execution,
        &request,
        &proof,
        deadline,
        cancellation.as_mut(),
    )
    .await;
    let credential_cleanup = revoke_new(&oidc, &transport, &tokens).await;
    Ok(RepairOutcome {
        maintenance,
        credential_cleanup,
    })
}

/// Retain one closed authorization transaction and its exact callback/exchange binding.
struct PendingAuthorization {
    transport: AuthTransport,
    oidc: AuthorizationClient,
    callback: CallbackListener,
    require_issuer: bool,
    state: CsrfToken,
    nonce: Nonce,
    verifier: openidconnect::PkceCodeVerifier,
    ready: AuthorizationReady,
}

/// Discover only the trusted installation and prepare its single public-client flow.
async fn prepare_authorization(
    host: &HostContext,
    deadline: Instant,
    mut cancellation: Pin<&mut (impl Future<Output = ()> + Send)>,
) -> Result<PendingAuthorization, RepairFailure> {
    let client = host
        .options_copy()
        .human_auth_client(&host.api, &host.issuer)
        .map_err(|_| failure(FailureKind::InvalidContext, CleanupStatus::NotNeeded))?;
    let installation = within(
        deadline,
        cancellation.as_mut(),
        discover(&host.api, host.options_copy()),
    )
    .await
    .map_err(|kind| failure(kind, CleanupStatus::NotNeeded))?
    .map_err(|_| failure(FailureKind::Discovery, CleanupStatus::NotNeeded))?;
    if installation.resource != host.api
        || installation.installation_id != host.installation_id
        || installation.provider.issuer().as_str() != host.issuer
        || installation.client_id != host.client_id
    {
        return Err(failure(FailureKind::Binding, CleanupStatus::NotNeeded));
    }
    let transport = AuthTransport::new(client, &installation)
        .map_err(|_| failure(FailureKind::InvalidContext, CleanupStatus::NotNeeded))?;
    let require_issuer = installation
        .provider
        .additional_metadata()
        .authorization_response_iss_parameter_supported;
    let callback = within(
        deadline,
        cancellation.as_mut(),
        CallbackListener::bind(host.issuer.clone()),
    )
    .await
    .map_err(|kind| failure(kind, CleanupStatus::NotNeeded))?
    .map_err(|_| failure(FailureKind::Callback, CleanupStatus::NotNeeded))?;
    let callback_uri = callback
        .redirect_uri()
        .map_err(|_| failure(FailureKind::Callback, CleanupStatus::NotNeeded))?;
    let oidc = CoreClient::from_provider_metadata(
        installation.provider,
        ClientId::new(host.client_id.clone()),
        None,
    )
    .set_redirect_uri(
        RedirectUrl::new(callback_uri.clone())
            .map_err(|_| failure(FailureKind::InvalidContext, CleanupStatus::NotNeeded))?,
    )
    .set_revocation_url(
        RevocationUrl::new(transport.revocation_url().to_string())
            .map_err(|_| failure(FailureKind::InvalidContext, CleanupStatus::NotNeeded))?,
    );
    let (challenge, verifier) = PkceCodeChallenge::new_random_sha256();
    let (authorization_url, state, nonce) = oidc
        .authorize_url(
            AuthenticationFlow::<CoreResponseType>::AuthorizationCode,
            CsrfToken::new_random,
            Nonce::new_random,
        )
        .add_scope(Scope::new("inframeld:api".into()))
        .add_extra_param("audience", &host.api)
        .set_pkce_challenge(challenge)
        .url();
    let ready = AuthorizationReady {
        authorization_url,
        issuer: host.issuer.clone(),
        callback_uri,
    };
    Ok(PendingAuthorization {
        transport,
        oidc,
        callback,
        require_issuer,
        state,
        nonce,
        verifier,
        ready,
    })
}

impl HostContext {
    /// Validate repair intent before discovery, browser or maintenance effects.
    fn bound_request(&self, request: &[u8]) -> Result<RepairRequest, RepairFailure> {
        let request = RepairRequest::parse(request)
            .map_err(|_| failure(FailureKind::InvalidRequest, CleanupStatus::NotNeeded))?;
        if request.expected_installation_id != self.installation_id
            || request.expected_identity_id != self.identity_id
        {
            return Err(failure(FailureKind::Binding, CleanupStatus::NotNeeded));
        }
        if self.client_id != "inframeld-cli" {
            return Err(failure(
                FailureKind::InvalidContext,
                CleanupStatus::NotNeeded,
            ));
        }
        Ok(request)
    }
    fn options_copy(&self) -> DiscoveryOptions {
        DiscoveryOptions {
            certificate_authorities: self.options.certificate_authorities.clone(),
            proxy: self.options.proxy.clone(),
        }
    }
}

type AuthorizationClient = CoreClient<
    EndpointSet,
    EndpointNotSet,
    EndpointNotSet,
    EndpointSet,
    EndpointMaybeSet,
    EndpointMaybeSet,
>;

/// Poll the same absolute interaction deadline at every stage. Cancellation
/// cleanup has its own finite budget and never restarts authorization.
async fn within<T>(
    deadline: Instant,
    cancellation: Pin<&mut (impl Future<Output = ()> + Send)>,
    operation: impl Future<Output = T>,
) -> Result<T, FailureKind> {
    tokio::select! {
        biased;
        ()=cancellation=>Err(FailureKind::Cancelled),
        ()=tokio::time::sleep_until(deadline)=>Err(FailureKind::TimedOut),
        result=operation=>Ok(result),
    }
}
fn failure(kind: FailureKind, credential_cleanup: CleanupStatus) -> RepairFailure {
    RepairFailure {
        kind,
        credential_cleanup,
        resource_cleanup: CleanupStatus::NotNeeded,
    }
}

/// Use only verified claims. The maintained library intentionally leaves azp
/// interpretation to its caller, so the official-client check remains explicit.
fn validate_identity(
    client: &AuthorizationClient,
    tokens: &CoreTokenResponse,
    nonce: &Nonce,
    host: &HostContext,
) -> Result<(), ()> {
    if tokens.token_type() != &CoreTokenType::Bearer || tokens.access_token().secret().is_empty() {
        return Err(());
    }
    let verifier = client.id_token_verifier();
    let id_token = tokens.id_token().ok_or(())?;
    let claims = id_token.claims(&verifier, nonce).map_err(|_| ())?;
    if Uuid::parse_str(claims.subject().as_str()).map_err(|_| ())? != host.identity_id
        || claims
            .authorized_party()
            .is_some_and(|party| party.as_str() != host.client_id)
        || (claims.audiences().len() > 1 && claims.authorized_party().is_none())
    {
        return Err(());
    }
    if let Some(expected) = claims.access_token_hash() {
        let actual = AccessTokenHash::from_token(
            tokens.access_token(),
            id_token.signing_alg().map_err(|_| ())?,
            id_token.signing_key(&verifier).map_err(|_| ())?,
        )
        .map_err(|_| ())?;
        if actual != *expected {
            return Err(());
        }
    }
    Ok(())
}

/// Revoke only this invocation's newly issued credentials, without cancellation
/// or retry reopening the operation. Standard revocation is bounded as one unit.
async fn revoke_new(
    client: &AuthorizationClient,
    transport: &AuthTransport,
    tokens: &CoreTokenResponse,
) -> CleanupStatus {
    let revoking = async {
        let refresh_confirmed = if let Some(refresh) = tokens.refresh_token() {
            match client.revoke_token(CoreRevocableToken::RefreshToken(refresh.clone())) {
                Ok(request) => request.request_async(transport).await.is_ok(),
                Err(_) => false,
            }
        } else {
            true
        };
        // A rejected refresh revocation must not skip the independent access
        // credential cleanup while the same finite cleanup budget remains.
        let access_confirmed = match client.revoke_token(CoreRevocableToken::AccessToken(
            tokens.access_token().clone(),
        )) {
            Ok(request) => request.request_async(transport).await.is_ok(),
            Err(_) => false,
        };
        refresh_confirmed && access_confirmed
    };
    if matches!(
        tokio::time::timeout(Duration::from_secs(5), revoking).await,
        Ok(true)
    ) {
        CleanupStatus::Confirmed
    } else {
        CleanupStatus::Unconfirmed
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn trusted_host_context_is_explicit_strict_and_never_exposes_proxy_diagnostics() {
        let input=br#"{"schemaVersion":1,"api":"https://api.test/api","issuer":"https://identity.test/","clientId":"inframeld-cli","installationId":"00000000-0000-0000-0000-000000000001","expectedIdentityId":"00000000-0000-0000-0000-000000000002","certificateAuthorities":[],"proxy":null}"#;
        assert!(HostContext::parse(input).is_ok());
        for invalid in [
            br#"{"schemaVersion":1,"api":"https://api.test/api","issuer":"https://identity.test/","clientId":"other-client","installationId":"00000000-0000-0000-0000-000000000001","expectedIdentityId":"00000000-0000-0000-0000-000000000002"}"#.as_slice(),
            br#"{"schemaVersion":1,"schemaVersion":1,"api":"https://api.test/api","issuer":"https://identity.test/","clientId":"inframeld-cli","installationId":"00000000-0000-0000-0000-000000000001","expectedIdentityId":"00000000-0000-0000-0000-000000000002"}"#.as_slice(),
            br#"{"schemaVersion":1,"api":"https://api.test/api","issuer":"https://identity.test/","clientId":"inframeld-cli","installationId":"00000000-0000-0000-0000-000000000001","expectedIdentityId":"00000000-0000-0000-0000-000000000002","token":"never-accepted"}"#.as_slice(),
        ] {
            assert!(HostContext::parse(invalid).is_err());
        }
    }
}
