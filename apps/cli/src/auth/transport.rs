//! Adapt maintained OAuth requests and generated session calls to one frozen TLS policy.

use std::{future::Future, pin::Pin};

use futures_util::StreamExt;
use inframeld_sdk::{HttpClient, client::ApiOpError};
use url::Url;
use uuid::Uuid;

use crate::discovery::DiscoveredInstallation;

const RESPONSE_LIMIT: usize = 64 * 1024;
const REQUEST_LIMIT: usize = 3 * RESPONSE_LIMIT + 1024;

/// Fixed categories discard protected provider/SDK errors at this boundary.
#[derive(Debug, Clone, Copy, thiserror::Error)]
pub(super) enum TransportError {
    #[error("The frozen OAuth endpoint profile is invalid.")]
    Endpoint,
    #[error("The protected transport did not complete.")]
    Transport,
    #[error("Protected transport redirects are forbidden.")]
    Redirect,
    #[error("The protected response exceeded its bound.")]
    ResponseTooLarge,
    #[error("The current session did not verify an admitted human.")]
    Session,
}

/// Reuse one credential-free client configured by the existing discovery owner.
pub(super) struct AuthTransport {
    client: reqwest::Client,
    api: String,
    token: Url,
    revocation: Url,
}
impl AuthTransport {
    pub(super) fn new(
        client: reqwest::Client,
        installation: &DiscoveredInstallation,
    ) -> Result<Self, TransportError> {
        let token = installation
            .provider
            .token_endpoint()
            .ok_or(TransportError::Endpoint)?
            .url()
            .clone();
        let revocation = installation
            .provider
            .additional_metadata()
            .revocation_endpoint
            .clone()
            .ok_or(TransportError::Endpoint)?;
        if token.origin() != installation.provider.issuer().url().origin()
            || revocation.origin() != token.origin()
        {
            return Err(TransportError::Endpoint);
        }
        Ok(Self {
            client,
            api: installation.resource.clone(),
            token,
            revocation,
        })
    }
    pub(super) fn revocation_url(&self) -> &Url {
        &self.revocation
    }

    /// Consume the shipped generated operation with the same frozen CA/proxy/client policy.
    pub(super) async fn session_principal(
        &self,
        token: &openidconnect::AccessToken,
    ) -> Result<Uuid, TransportError> {
        let sdk = HttpClient::with_client(self.client.clone())
            .with_base_url(self.api.clone())
            .with_api_key(token.secret().clone())
            .with_max_response_body_bytes(RESPONSE_LIMIT);
        sdk.get_current_session()
            .await
            .map(|response| response.body.principal_id)
            .map_err(|error| match error {
                ApiOpError::Api(_) => TransportError::Session,
                ApiOpError::Transport(_) => TransportError::Transport,
            })
    }

    /// Send only public-client form POSTs to the two frozen provider destinations.
    async fn request(
        &self,
        request: openidconnect::HttpRequest,
    ) -> Result<openidconnect::HttpResponse, TransportError> {
        let target = request.uri().to_string();
        if request.method() != http::Method::POST
            || (target != self.token.as_str() && target != self.revocation.as_str())
            || request.body().len() > REQUEST_LIMIT
            || request
                .headers()
                .keys()
                .any(|name| name != http::header::ACCEPT && name != http::header::CONTENT_TYPE)
            || request
                .headers()
                .get(http::header::CONTENT_TYPE)
                .is_none_or(|value| value != "application/x-www-form-urlencoded")
        {
            return Err(TransportError::Endpoint);
        }
        let response = self
            .client
            .post(target)
            .headers(request.headers().clone())
            .body(request.body().clone())
            .send()
            .await
            .map_err(|_| TransportError::Transport)?;
        if response.status().is_redirection() {
            return Err(TransportError::Redirect);
        }
        let mut builder = http::Response::builder().status(response.status());
        *builder.headers_mut().ok_or(TransportError::Transport)? = response.headers().clone();
        let mut body = Vec::new();
        let mut chunks = std::pin::pin!(response.bytes_stream());
        while let Some(chunk) = chunks.next().await {
            let chunk = chunk.map_err(|_| TransportError::Transport)?;
            if chunk.len() > RESPONSE_LIMIT - body.len() {
                return Err(TransportError::ResponseTooLarge);
            }
            body.extend_from_slice(&chunk);
        }
        builder.body(body).map_err(|_| TransportError::Transport)
    }
}
impl<'a> openidconnect::AsyncHttpClient<'a> for AuthTransport {
    type Error = TransportError;
    type Future =
        Pin<Box<dyn Future<Output = Result<openidconnect::HttpResponse, Self::Error>> + Send + 'a>>;
    fn call(&'a self, request: openidconnect::HttpRequest) -> Self::Future {
        Box::pin(self.request(request))
    }
}
