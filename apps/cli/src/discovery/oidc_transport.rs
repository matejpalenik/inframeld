//! Apply the same bounded HTTP policy to API metadata and provider requests.

use std::{future::Future, pin::Pin, time::Duration};

use futures_util::StreamExt;
use url::Origin;

use super::{
    BODY_LIMIT, DiscoveryError, DiscoveryOptions,
    error::transport_error,
    url_policy::{UrlPolicy, parse_provider_url},
};

/// Build a fresh transport without ambient proxies, credentials, redirects or retries.
pub(super) fn client(
    options: DiscoveryOptions,
    request_budget: Duration,
) -> Result<reqwest::Client, DiscoveryError> {
    let mut builder = reqwest::Client::builder()
        .no_proxy()
        .timeout(request_budget)
        .redirect(reqwest::redirect::Policy::none())
        .retry(reqwest::retry::never());
    for certificate in options.certificate_authorities {
        builder = builder.add_root_certificate(certificate);
    }
    if let Some(proxy) = options.proxy {
        builder = builder.proxy(proxy);
    }
    builder.build().map_err(|_| DiscoveryError::Transport)
}

/// Own the provider client and its exact issuer-origin and URL restrictions.
pub(super) struct OidcTransport {
    client: reqwest::Client,
    origin: Origin,
    policy: UrlPolicy,
}

impl OidcTransport {
    /// Bind one configured client to the issuer origin admitted by API metadata.
    pub(super) fn new(client: reqwest::Client, origin: Origin, policy: UrlPolicy) -> Self {
        Self {
            client,
            origin,
            policy,
        }
    }

    /// Admit only same-origin GETs, then read a bounded successful JSON response.
    async fn request(
        &self,
        request: openidconnect::HttpRequest,
    ) -> Result<openidconnect::HttpResponse, DiscoveryError> {
        let raw = request.uri().to_string();
        if parse_provider_url(&raw)?.origin() != self.origin {
            return Err(DiscoveryError::IdentityMismatch);
        }
        let target = self.policy.provider_url(&raw)?;
        if target.origin() != self.origin || request.method() != http::Method::GET {
            return Err(DiscoveryError::IdentityMismatch);
        }
        let response = self
            .client
            .get(target)
            .header("Accept", "application/json")
            .send()
            .await
            .map_err(|error| transport_error(&error))?;
        if response.status().is_redirection() {
            return Err(DiscoveryError::Redirect);
        }
        if !response.status().is_success() {
            return Err(DiscoveryError::Unavailable);
        }
        let mut output = http::Response::builder().status(response.status());
        *output
            .headers_mut()
            .ok_or(DiscoveryError::InvalidMetadata)? = response.headers().clone();
        let mut body = Vec::new();
        let mut chunks = std::pin::pin!(response.bytes_stream());
        while let Some(chunk) = chunks.next().await {
            let chunk = chunk.map_err(|error| transport_error(&error))?;
            if chunk.len() > BODY_LIMIT - body.len() {
                return Err(DiscoveryError::ResponseTooLarge);
            }
            body.extend_from_slice(&chunk);
        }
        output
            .body(body)
            .map_err(|_| DiscoveryError::InvalidMetadata)
    }
}

impl<'c> openidconnect::AsyncHttpClient<'c> for OidcTransport {
    type Error = DiscoveryError;
    type Future = Pin<
        Box<dyn Future<Output = Result<openidconnect::HttpResponse, DiscoveryError>> + Send + 'c>,
    >;

    fn call(&'c self, request: openidconnect::HttpRequest) -> Self::Future {
        Box::pin(self.request(request))
    }
}
