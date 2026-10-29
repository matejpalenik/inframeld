//! Classify failures without retaining upstream bodies or credential-bearing errors.

use std::{error::Error, fmt};

use inframeld_sdk::client::{ApiOpError, HttpError};

/// A discovery failure safe for human or machine presentation.
#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum DiscoveryError {
    /// The supplied identifier is not an allowed public URL.
    #[error("provide a canonical HTTPS API URL without credentials, query or fragment")]
    InvalidUrl,
    /// Public identity disagrees with the requested profile.
    #[error("discovery identity does not match the requested installation")]
    IdentityMismatch,
    /// Metadata is malformed or lacks required protocol configuration.
    #[error("invalid discovery metadata")]
    InvalidMetadata,
    /// The server advertises an unsupported first-party profile.
    #[error("unsupported discovery profile or transport configuration")]
    UnsupportedProfile,
    /// The server did not return successful metadata.
    #[error("discovery metadata is unavailable")]
    Unavailable,
    /// The TLS certificate could not be verified.
    #[error("discovery TLS verification failed")]
    Tls,
    /// Discovery never follows redirects.
    #[error("discovery redirects are not permitted")]
    Redirect,
    /// A response exceeded the fixed discovery budget.
    #[error("discovery response exceeds 64 KiB")]
    ResponseTooLarge,
    /// A per-request or overall deadline elapsed.
    #[error("discovery timed out")]
    Timeout,
    /// A connection failed without a usable response.
    #[error("discovery connection failed")]
    Transport,
}

/// Walk structured causes without preserving or searching arbitrary error text.
pub(super) fn transport_error(error: &(dyn Error + 'static)) -> DiscoveryError {
    let mut source: Option<&(dyn Error + 'static)> = Some(error);
    while let Some(item) = source {
        if item
            .downcast_ref::<reqwest::Error>()
            .is_some_and(reqwest::Error::is_timeout)
        {
            return DiscoveryError::Timeout;
        }
        if let Some(inner) = item
            .downcast_ref::<std::io::Error>()
            .and_then(std::io::Error::get_ref)
        {
            let classified = transport_error(inner);
            if classified != DiscoveryError::Transport {
                return classified;
            }
        }
        if matches!(
            item.downcast_ref::<rustls::Error>(),
            Some(rustls::Error::InvalidCertificate(_))
        ) {
            return DiscoveryError::Tls;
        }
        source = item.source();
    }
    DiscoveryError::Transport
}

/// Classify SDK input, status and transport failures without retaining their messages.
pub(super) fn sdk_error<E: fmt::Debug>(error: ApiOpError<E>) -> DiscoveryError {
    match error {
        ApiOpError::Transport(HttpError::Serialization(_)) => DiscoveryError::InvalidUrl,
        ApiOpError::Transport(HttpError::ResponseTooLarge { .. }) => {
            DiscoveryError::ResponseTooLarge
        }
        ApiOpError::Transport(HttpError::Network(error)) => transport_error(&error),
        ApiOpError::Transport(HttpError::Timeout) => DiscoveryError::Timeout,
        ApiOpError::Transport(HttpError::Middleware(error)) if error.is_timeout() => {
            DiscoveryError::Timeout
        }
        ApiOpError::Transport(error) => transport_error(&error),
        ApiOpError::Api(error) if (300..400).contains(&error.status) => DiscoveryError::Redirect,
        ApiOpError::Api(error) if error.status == 200 => DiscoveryError::InvalidMetadata,
        ApiOpError::Api(_) => DiscoveryError::Unavailable,
    }
}

#[cfg(test)]
mod tests {
    use super::{ApiOpError, DiscoveryError, HttpError, sdk_error};

    #[test]
    fn serialization_rejection_is_a_safe_input_error() {
        let sentinel = "private-discovery-credential";
        let error = sdk_error::<()>(ApiOpError::Transport(HttpError::Serialization(
            sentinel.to_owned(),
        )));
        assert_eq!(error, DiscoveryError::InvalidUrl);
        assert!(!error.to_string().contains(sentinel));
        assert!(!format!("{error:?}").contains(sentinel));
        assert!(std::error::Error::source(&error).is_none());
    }
}
