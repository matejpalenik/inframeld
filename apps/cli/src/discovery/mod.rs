//! Discover one installation without loading credentials or saving local state.
//!
//! [`discover()`] validates the exact API identity, its provider profile and public
//! signing keys. A successful result is public configuration, not login,
//! permission or release-compatibility evidence. The caller supplies a Tokio runtime.

mod discover;
mod error;
mod installation;
mod oidc_transport;
mod url_policy;

use url::Origin;
use uuid::Uuid;

pub(crate) use discover::discover_with_context;
pub use error::DiscoveryError;
pub use installation::{
    DiscoveredInstallation, DiscoveryOptions, DiscoveryProviderMetadata, ProviderExtensions,
};

/// One response budget shared by generated API calls and provider body reads.
const BODY_LIMIT: usize = 64 * 1024;

/// Validate an installation's public identity and login configuration over HTTPS.
///
/// The exact API URL must match the server's advertised resource identity. Reads
/// application metadata, provider metadata and public signing keys without loading
/// saved credentials, persisting a target or starting login. Requires a Tokio runtime.
///
/// # Limits
/// Allows ten seconds overall, five per request and 64 KiB per response.
/// Redirects and automatic retries are disabled. Additional trusted CAs and an
/// explicit proxy may be supplied through [`DiscoveryOptions`].
///
/// # Errors
/// Returns a [`DiscoveryError`] for invalid URLs, mismatched identities,
/// unsupported profiles, malformed metadata or failed transport. Upstream
/// response text is not included in the safe error category.
///
/// # Examples
/// Call from an existing Tokio runtime with an operator-supplied API identity.
/// This example compiles without contacting the external installation.
/// ```no_run
/// use inframeld_cli::discovery::{DiscoveryError, DiscoveryOptions, discover};
///
/// # async fn example() -> Result<(), DiscoveryError> {
/// let installation = discover(
///     "https://inframeld.company.example/api/v1",
///     DiscoveryOptions::default(),
/// ).await?;
/// assert_eq!(installation.client_id, "inframeld-cli");
/// # Ok(())
/// # }
/// ```
pub async fn discover(
    api_identity: &str,
    options: DiscoveryOptions,
) -> Result<DiscoveredInstallation, DiscoveryError> {
    discover_with_context(api_identity, options, None).await
}

/// Trusted managed-runtime identity, separate from untrusted returned metadata.
///
/// Only the managed-runtime owner may supply this context. There is deliberately
/// no public constructor, HTTP flag or deserialization path. #162 owns its creation.
#[derive(Debug, Clone)]
pub(crate) struct ManagedLocalContext {
    installation_id: Uuid,
    api_origin: Origin,
    issuer_origin: Origin,
}

#[cfg(test)]
mod transport_tests;
