//! Explicit connection inputs, separate from future saved target selection.

/// Caller-supplied connection to an installation. This does not establish trust or access.
#[derive(Debug, Clone)]
pub struct Connection {
    pub(crate) base_url: String,
}

impl Connection {
    /// Parse an API base URL. Target discovery and HTTPS policy belong to target registration.
    ///
    /// # Errors
    /// Rejects invalid URLs, credentials, query strings, fragments and non-HTTP schemes.
    pub fn new(base_url: &str) -> Result<Self, InvalidConnection> {
        let parsed = url::Url::parse(base_url).map_err(|_| InvalidConnection)?;
        if !matches!(parsed.scheme(), "http" | "https")
            || parsed.host_str().is_none()
            || !parsed.username().is_empty()
            || parsed.password().is_some()
            || parsed.query().is_some()
            || parsed.fragment().is_some()
        {
            return Err(InvalidConnection);
        }
        Ok(Self {
            base_url: parsed.as_str().trim_end_matches('/').to_owned(),
        })
    }
}

/// Connection input cannot be used as an HTTP API base URL.
#[derive(Debug, thiserror::Error)]
#[error("provide an HTTP(S) API base URL without credentials, query or fragment")]
pub struct InvalidConnection;
