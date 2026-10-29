//! Validate canonical identifiers under HTTPS or the sealed managed-local policy.

use url::{Origin, Url};

use super::{DiscoveryError, ManagedLocalContext};

/// The existing trusted context used consistently across API and provider checks.
#[derive(Debug, Clone)]
pub(super) struct UrlPolicy {
    managed: Option<ManagedLocalContext>,
}

impl UrlPolicy {
    /// Capture supplied trust facts without creating a new managed identity.
    pub(super) fn new(managed: Option<&ManagedLocalContext>) -> Self {
        Self {
            managed: managed.cloned(),
        }
    }

    /// Check the API under HTTPS or the exact managed API-origin restriction.
    pub(super) fn api_url(&self, value: &str) -> Result<Url, DiscoveryError> {
        match &self.managed {
            Some(context) => managed_url(value, &context.api_origin),
            None => validate_url(value),
        }
    }

    /// Check provider destinations under HTTPS or the exact managed issuer origin.
    pub(super) fn issuer_url(&self, value: &str) -> Result<Url, DiscoveryError> {
        match &self.managed {
            Some(context) => managed_url(value, &context.issuer_origin),
            None => validate_url(value),
        }
    }
}

/// Reject ambiguous URL syntax while the caller retains the original identity text.
pub(super) fn parse_identifier(value: &str) -> Result<Url, DiscoveryError> {
    let authority = value
        .split_once("://")
        .filter(|(scheme, _)| {
            scheme.eq_ignore_ascii_case("https") || scheme.eq_ignore_ascii_case("http")
        })
        .map(|(_, authority)| authority)
        .ok_or(DiscoveryError::InvalidUrl)?;
    if authority
        .split(['/', '?', '#'])
        .next()
        .is_none_or(|host| host.is_empty() || host.contains('@'))
    {
        return Err(DiscoveryError::InvalidUrl);
    }
    let url = Url::parse(value).map_err(|_| DiscoveryError::InvalidUrl)?;
    let raw_path = value
        .split_once("://")
        .and_then(|(_, rest)| rest.split_once('/'))
        .map_or("", |(_, path)| path);
    if raw_path.bytes().enumerate().any(|(i, byte)| {
        byte == b'%'
            && !raw_path
                .as_bytes()
                .get(i + 1..i + 3)
                .is_some_and(|hex| hex.iter().all(u8::is_ascii_hexdigit))
    }) {
        return Err(DiscoveryError::InvalidUrl);
    }
    let decoded = percent_encoding::percent_decode_str(raw_path)
        .decode_utf8()
        .map_err(|_| DiscoveryError::InvalidUrl)?;
    if value.len() > 8192
        || decoded.chars().any(|c| c.is_control() || c == '\\')
        || url.host_str().is_none()
        || !url.username().is_empty()
        || url.password().is_some()
        || url.query().is_some()
        || url.fragment().is_some()
        || value.contains('\\')
        || value.chars().any(|c| c.is_whitespace() || c.is_control())
        || decoded.split('/').any(|part| matches!(part, "." | ".."))
    {
        return Err(DiscoveryError::InvalidUrl);
    }
    Ok(url)
}

fn validate_url(value: &str) -> Result<Url, DiscoveryError> {
    let url = parse_identifier(value)?;
    if url.scheme() != "https" {
        return Err(DiscoveryError::InvalidUrl);
    }
    Ok(url)
}

fn managed_url(value: &str, expected: &Origin) -> Result<Url, DiscoveryError> {
    let url = parse_identifier(value)?;
    let literal_host = value
        .strip_prefix("http://")
        .and_then(|rest| rest.split('/').next())
        .and_then(|authority| authority.split(':').next());
    if literal_host != Some("127.0.0.1") || url.scheme() != "http" || &url.origin() != expected {
        return Err(DiscoveryError::InvalidUrl);
    }
    Ok(url)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    #[test]
    fn unsafe_targets_are_rejected_before_network_io() {
        for value in [
            "http://127.0.0.1:8000",
            "https://u:secret@api.test",
            "https://api.test?x=secret",
            "https://api.test/#frag",
            "https://api.test/../admin",
            "https://api.test/%2e%2e/admin",
            "https:/api.test/../admin",
            "https:api.test",
            "https:/api.test/path://placeholder",
            "https://@api.test",
            "https://api.test/a%GG",
            "https://api.test/a%",
            "https://api%GG.test",
            "https://api%2Fadmin.test",
            "https://api%00.test",
            "https://api%5C.test",
        ] {
            assert_eq!(validate_url(value).unwrap_err(), DiscoveryError::InvalidUrl);
        }
    }

    #[test]
    fn exact_identifier_spelling_is_retained() {
        assert!(validate_url("https://api.test/api/").is_ok());
        assert!(validate_url("https://private.test:8443/api").is_ok());
        assert!(validate_url("HTTPS://api.test").is_ok());
        for value in [
            "https://api.test",
            "HTTPS://API.test:443/api/",
            "https://private.test:8443/api",
            "https://10.0.0.1/api",
            "https://[2001:db8::1]/api",
            "https://bücher.test/a%20b",
            "https://xn--bcher-kva.test/api",
            "https://%61pi.test/api%2Fv1",
            "https://api.test/a%25b",
            "https://api.test:0/api",
        ] {
            assert!(validate_url(value).is_ok(), "rejected {value}");
        }
    }

    #[test]
    fn identifier_budget_counts_original_utf8_bytes() {
        let prefix = "https://api.test/";
        for character in ['a', 'é'] {
            for size in [8192, 8193] {
                let bytes = size - prefix.len();
                let path = character.to_string().repeat(bytes / character.len_utf8());
                let remainder = "a".repeat(bytes % character.len_utf8());
                let value = format!("{prefix}{path}{remainder}");
                assert_eq!(value.len(), size);
                if size == 8192 {
                    assert!(validate_url(&value).is_ok());
                } else {
                    assert_eq!(
                        validate_url(&value).unwrap_err(),
                        DiscoveryError::InvalidUrl
                    );
                }
            }
        }
    }

    #[test]
    fn managed_discovery_rejects_normalized_loopback_aliases() {
        let literal = "http://127.0.0.1:8000";
        let origin = Url::parse(literal).unwrap().origin();
        assert!(managed_url(literal, &origin).is_ok());
        for value in [
            "HTTP://127.0.0.1:8000",
            "http://127.1:8000",
            "http://2130706433:8000",
            "http://%31%32%37.0.0.1:8000",
            "http://127.0.0.1.:8000",
        ] {
            assert_eq!(
                managed_url(value, &origin).unwrap_err(),
                DiscoveryError::InvalidUrl,
                "accepted {value}",
            );
        }
    }
}
