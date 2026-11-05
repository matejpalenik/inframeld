//! Bind authorization responses to the exact issuer, state and loopback endpoint.

use std::{
    collections::HashSet,
    convert::Infallible,
    pin::Pin,
    sync::{
        Mutex,
        atomic::{AtomicBool, Ordering},
    },
    task::{Context, Poll},
    time::Duration,
};

use bytes::Bytes;
use futures_util::{StreamExt, stream::FuturesUnordered};
use http_body_util::Full;
use hyper::{Request, Response, body::Incoming, service::service_fn};
use hyper_util::rt::TokioIo;
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, ReadBuf},
    net::TcpStream,
    time::Instant,
};
use zeroize::Zeroizing;

use openidconnect::{AuthorizationCode, CsrfToken};
use sha2::{Digest, Sha256};

/// Maximum raw request target, separate from header and parser budgets.
///
/// The maintained `http` 1.5 URI parser additionally rejects targets over 65,534
/// bytes. The full supported issuer still fits after worst-case form encoding.
pub const REQUEST_TARGET_LIMIT: usize = 128 * 1024;

/// Derive the registered callback path from the original trusted issuer bytes.
#[must_use]
pub fn issuer_callback_path(issuer: &str) -> String {
    format!("/oauth/callback/{:x}", Sha256::digest(issuer.as_bytes()))
}

/// Safe callback failure categories omit response content and credentials.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum CallbackError {
    /// The request cannot belong to the pending authorization transaction.
    #[error("The authorization callback did not match the pending transaction.")]
    InvalidResponse,
    /// The original interaction or per-connection budget expired.
    #[error("The authorization callback deadline expired.")]
    Timeout,
    /// All eight accepted connections were consumed without a valid response.
    #[error("The authorization callback connection budget was exhausted.")]
    ConnectionLimit,
    /// The private listener could not complete its local I/O.
    #[error("The private authorization callback listener was unavailable.")]
    Unavailable,
}

/// An admitted response contains either a protected code or a safe denial category.
#[derive(Debug)]
pub enum CallbackResponse {
    /// A single code whose exchange remains owned by the authorization operation.
    Code(AuthorizationCode),
    /// The provider declined authorization after all callback bindings were checked.
    Denied,
}

/// Own one ephemeral literal-loopback listener until its single callback is consumed.
#[derive(Debug)]
pub struct CallbackListener {
    listener: tokio::net::TcpListener,
    issuer: String,
}

impl CallbackListener {
    /// Bind only IPv4 loopback after the caller has validated its complete intent.
    ///
    /// # Errors
    /// Returns a safe category if the private listener cannot be created.
    pub async fn bind(issuer: String) -> Result<Self, CallbackError> {
        let listener = tokio::net::TcpListener::bind((std::net::Ipv4Addr::LOCALHOST, 0))
            .await
            .map_err(|_| CallbackError::Unavailable)?;
        Ok(Self { listener, issuer })
    }

    /// Return the complete URI whose exact bytes must also be used in code exchange.
    ///
    /// # Errors
    /// Returns a safe category if the owned listener address is unavailable.
    pub fn redirect_uri(&self) -> Result<String, CallbackError> {
        let address = self
            .listener
            .local_addr()
            .map_err(|_| CallbackError::InvalidResponse)?;
        Ok(format!(
            "http://127.0.0.1:{}{}",
            address.port(),
            issuer_callback_path(&self.issuer)
        ))
    }

    /// Await one valid response within the original operation deadline.
    ///
    /// # Errors
    /// Returns a safe category for invalid, exhausted or expired callback acquisition.
    pub async fn receive(
        self,
        state: CsrfToken,
        require_issuer: bool,
        deadline: Instant,
    ) -> Result<CallbackResponse, CallbackError> {
        let address = self
            .listener
            .local_addr()
            .map_err(|_| CallbackError::Unavailable)?;
        let binding = CallbackBinding::new(self.issuer, state, address.port(), require_issuer);
        let consumed = AtomicBool::new(false);
        let mut accepted = 0;
        let mut connections = FuturesUnordered::new();
        loop {
            if accepted == 8 && connections.is_empty() {
                return Err(CallbackError::ConnectionLimit);
            }
            tokio::select! {
                biased;
                () = tokio::time::sleep_until(deadline) => return Err(CallbackError::Timeout),
                Some(result) = connections.next(), if !connections.is_empty() => {
                    if let Ok(response) = result {
                        // Dropping the remaining in-place futures closes their owned sockets.
                        // No request handlers are detached from this single-use operation.
                        return Ok(response);
                    }
                }
                connection = self.listener.accept(), if accepted < 8 => {
                    let (socket, peer) = connection.map_err(|_| CallbackError::Unavailable)?;
                    accepted += 1;
                    if connections.len() < 2
                        && peer.ip() == std::net::Ipv4Addr::LOCALHOST
                        && socket.local_addr().ok() == Some(address)
                    {
                        connections.push(serve_connection(
                            socket, &binding, &consumed,
                            deadline.min(Instant::now() + Duration::from_secs(5)),
                        ));
                    }
                    // A busy, auxiliary or invalid connection still consumes the total budget.
                }
            }
        }
    }
}

/// Frozen expectations for one pending authorization response.
#[derive(Debug)]
pub struct CallbackBinding {
    issuer: String,
    state: CsrfToken,
    host: String,
    path: String,
    require_issuer: bool,
}

impl CallbackBinding {
    /// Capture the original issuer and unpredictable state for one actual port.
    #[must_use]
    pub fn new(issuer: String, state: CsrfToken, port: u16, require_issuer: bool) -> Self {
        Self {
            path: issuer_callback_path(&issuer),
            issuer,
            state,
            host: format!("127.0.0.1:{port}"),
            require_issuer,
        }
    }

    /// Validate a raw request target and exact Host before admitting exchange.
    ///
    /// # Errors
    /// Returns a safe category when any endpoint or transaction binding fails.
    pub fn validate(&self, target: &str, host: &str) -> Result<CallbackResponse, CallbackError> {
        let invalid = CallbackError::InvalidResponse;
        if target.len() > REQUEST_TARGET_LIMIT || target.contains('#') || host != self.host {
            return Err(invalid);
        }
        let (path, query) = target.split_once('?').ok_or(invalid)?;
        if path != self.path {
            return Err(invalid);
        }
        let parameters = CallbackParameters::parse(query)?;
        let state = parameters.state.ok_or(invalid)?;
        if self.state != CsrfToken::new(state) {
            return Err(invalid);
        }
        match parameters.issuer {
            Some(issuer) if issuer != self.issuer => return Err(invalid),
            None if self.require_issuer => return Err(invalid),
            _ => {}
        }
        match (parameters.code, parameters.error) {
            (Some(code), None) if !code.is_empty() && !parameters.error_details => {
                Ok(CallbackResponse::Code(AuthorizationCode::new(code)))
            }
            (None, Some(error)) if !error.is_empty() => Ok(CallbackResponse::Denied),
            _ => Err(invalid),
        }
    }
}

const HEADER_BYTES_LIMIT: usize = 32 * 1024;
const HEADER_COUNT_LIMIT: usize = 32;
const PARSER_BUFFER_LIMIT: usize = 192 * 1024;

/// Bound raw header bytes before handing the unchanged request to Hyper's parser.
async fn serve_connection(
    socket: TcpStream,
    binding: &CallbackBinding,
    consumed: &AtomicBool,
    deadline: Instant,
) -> Result<CallbackResponse, CallbackError> {
    let deadline = deadline.min(Instant::now() + Duration::from_secs(5));
    let outcome = Mutex::new(None);
    let serving = tokio::time::timeout_at(deadline, async {
        let replay = ReplaySocket::read_headers(socket).await?;
        let service = service_fn(|request: Request<Incoming>| {
            let mut result = validate_request(&request, binding);
            if result.is_ok() && consumed.swap(true, Ordering::AcqRel) {
                result = Err(CallbackError::InvalidResponse);
            }
            let status = if result.is_ok() {
                http::StatusCode::OK
            } else {
                http::StatusCode::BAD_REQUEST
            };
            if let Ok(mut outcome) = outcome.lock() {
                *outcome = Some(result);
            }
            let mut response = Response::new(Full::new(Bytes::from_static(
                b"Authorization response received. You may close this window.",
            )));
            *response.status_mut() = status;
            response.headers_mut().insert(
                http::header::CACHE_CONTROL,
                http::HeaderValue::from_static("no-store"),
            );
            response.headers_mut().insert(
                http::header::CONTENT_TYPE,
                http::HeaderValue::from_static("text/plain; charset=utf-8"),
            );
            response.headers_mut().insert(
                http::header::CONTENT_SECURITY_POLICY,
                http::HeaderValue::from_static("default-src 'none'"),
            );
            std::future::ready(Ok::<_, Infallible>(response))
        });
        let mut builder = hyper::server::conn::http1::Builder::new();
        builder
            .keep_alive(false)
            .max_headers(HEADER_COUNT_LIMIT)
            .max_buf_size(PARSER_BUFFER_LIMIT)
            .header_read_timeout(None);
        builder
            .serve_connection(TokioIo::new(replay), service)
            .await
            .map_err(|_| CallbackError::InvalidResponse)?;
        Ok::<(), CallbackError>(())
    })
    .await;
    // Once admitted, browser response delivery cannot reopen this transaction.
    // The code remains bound even if the browser closes its response socket.
    if let Some(result) = outcome
        .into_inner()
        .map_err(|_| CallbackError::Unavailable)?
    {
        return result;
    }
    serving.map_err(|_| CallbackError::Timeout)??;
    Err(CallbackError::InvalidResponse)
}

/// Reject unexpected HTTP framing before checking the original callback binding.
fn validate_request(
    request: &Request<Incoming>,
    binding: &CallbackBinding,
) -> Result<CallbackResponse, CallbackError> {
    if request.method() != http::Method::GET
        || request.version() != http::Version::HTTP_11
        || request.headers().contains_key(http::header::CONTENT_LENGTH)
        || request
            .headers()
            .contains_key(http::header::TRANSFER_ENCODING)
        || request.headers().get_all(http::header::HOST).iter().count() != 1
    {
        return Err(CallbackError::InvalidResponse);
    }
    let host = request
        .headers()
        .get(http::header::HOST)
        .and_then(|host| host.to_str().ok())
        .ok_or(CallbackError::InvalidResponse)?;
    binding.validate(&request.uri().to_string(), host)
}

/// Retain the bounded wire prelude without replacing the maintained HTTP parser.
///
/// Raw header whitespace counts toward the header budget. The request line has
/// its own larger allowance so percent-encoded issuer values remain supported.
struct ReplaySocket {
    socket: TcpStream,
    prefix: Zeroizing<Vec<u8>>,
    position: usize,
}

impl ReplaySocket {
    /// Bound the wire prelude while retaining its bytes for the maintained HTTP parser.
    async fn read_headers(mut socket: TcpStream) -> Result<Self, CallbackError> {
        let mut prefix = Zeroizing::new(Vec::new());
        let mut chunk = [0_u8; 4096];
        loop {
            let read = socket
                .read(&mut chunk)
                .await
                .map_err(|_| CallbackError::Unavailable)?;
            if read == 0 || prefix.len() + read > PARSER_BUFFER_LIMIT {
                return Err(CallbackError::InvalidResponse);
            }
            prefix.extend_from_slice(&chunk[..read]);
            if let Some(end) = prefix.windows(4).position(|part| part == b"\r\n\r\n") {
                let line_end = prefix
                    .windows(2)
                    .position(|part| part == b"\r\n")
                    .ok_or(CallbackError::InvalidResponse)?;
                if line_end > REQUEST_TARGET_LIMIT + "GET  HTTP/1.1".len()
                    || end + 2 - (line_end + 2) > HEADER_BYTES_LIMIT
                {
                    return Err(CallbackError::InvalidResponse);
                }
                return Ok(Self {
                    socket,
                    prefix,
                    position: 0,
                });
            }
            if prefix.len() == PARSER_BUFFER_LIMIT {
                return Err(CallbackError::InvalidResponse);
            }
        }
    }
}

impl AsyncRead for ReplaySocket {
    fn poll_read(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &mut ReadBuf<'_>,
    ) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        if this.position < this.prefix.len() {
            let count = buffer.remaining().min(this.prefix.len() - this.position);
            buffer.put_slice(&this.prefix[this.position..this.position + count]);
            this.position += count;
            Poll::Ready(Ok(()))
        } else {
            Pin::new(&mut this.socket).poll_read(context, buffer)
        }
    }
}

impl AsyncWrite for ReplaySocket {
    fn poll_write(
        self: Pin<&mut Self>,
        context: &mut Context<'_>,
        buffer: &[u8],
    ) -> Poll<std::io::Result<usize>> {
        Pin::new(&mut self.get_mut().socket).poll_write(context, buffer)
    }
    fn poll_flush(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        Pin::new(&mut self.get_mut().socket).poll_flush(context)
    }
    fn poll_shutdown(self: Pin<&mut Self>, context: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        Pin::new(&mut self.get_mut().socket).poll_shutdown(context)
    }
}

/// Keep protocol parameters typed after the deliberately untrusted query boundary.
#[derive(Default)]
struct CallbackParameters {
    code: Option<String>,
    state: Option<String>,
    issuer: Option<String>,
    error: Option<String>,
    error_details: bool,
}

impl CallbackParameters {
    fn parse(query: &str) -> Result<Self, CallbackError> {
        let mut parameters = Self::default();
        let mut seen = HashSet::new();
        for pair in query.split('&') {
            let (name, value) = pair.split_once('=').ok_or(CallbackError::InvalidResponse)?;
            let name = decode_component(name)?;
            let value = decode_component(value)?;
            if name.is_empty() || !seen.insert(name.clone()) {
                return Err(CallbackError::InvalidResponse);
            }
            match name.as_str() {
                "code" => parameters.code = Some(value),
                "state" => parameters.state = Some(value),
                "iss" => parameters.issuer = Some(value),
                "error" => parameters.error = Some(value),
                "error_description" | "error_uri" => parameters.error_details = true,
                // OAuth clients ignore extensions, but never retain or trust their values.
                _ => {}
            }
        }
        Ok(parameters)
    }
}

fn decode_component(value: &str) -> Result<String, CallbackError> {
    if value.bytes().enumerate().any(|(index, byte)| {
        byte == b'%'
            && !value
                .as_bytes()
                .get(index + 1..index + 3)
                .is_some_and(|hex| hex.iter().all(u8::is_ascii_hexdigit))
    }) {
        return Err(CallbackError::InvalidResponse);
    }
    let spaces = value.replace('+', " ");
    percent_encoding::percent_decode_str(&spaces)
        .decode_utf8()
        .map(std::borrow::Cow::into_owned)
        .map_err(|_| CallbackError::InvalidResponse)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]

    use super::*;
    use std::fmt::Write as _;

    #[derive(serde::Deserialize)]
    struct Vector {
        issuer: String,
        path: String,
    }

    #[test]
    fn callback_hash_preserves_exact_utf8_issuer_spelling() {
        let vectors: Vec<Vector> = serde_json::from_str(include_str!(
            "../../../../contracts/fixtures/human-cli-issuer-callbacks.json"
        ))
        .unwrap();
        for vector in vectors {
            assert_eq!(issuer_callback_path(&vector.issuer), vector.path);
        }
    }

    fn binding(require_issuer: bool) -> CallbackBinding {
        CallbackBinding::new(
            "https://identity.test/".into(),
            CsrfToken::new("expected-state".into()),
            52731,
            require_issuer,
        )
    }

    fn target(query: &str) -> String {
        format!("{}?{query}", issuer_callback_path("https://identity.test/"))
    }

    #[test]
    fn code_and_denial_require_the_same_endpoint_state_and_optional_issuer_rules() {
        let host = "127.0.0.1:52731";
        assert!(matches!(
            binding(false).validate(&target("code=secret-code&state=expected-state"), host),
            Ok(CallbackResponse::Code(_))
        ));
        assert!(matches!(
            binding(false).validate(&target("error=access_denied&state=expected-state"), host),
            Ok(CallbackResponse::Denied)
        ));
        let exact = "state=expected-state&iss=https%3A%2F%2Fidentity.test%2F";
        assert!(
            binding(true)
                .validate(&target(&format!("code=secret-code&{exact}")), host)
                .is_ok()
        );
        assert!(
            binding(true)
                .validate(&target(&format!("error=access_denied&{exact}")), host)
                .is_ok()
        );
        for query in [
            "code=secret-code&state=wrong",
            "code=secret-code&state=expected-state&state=expected-state",
            "code=secret-code&state=expected-state&code=other",
            "code=secret-code&state=expected-state&error=access_denied",
            "code=secret-code&state=expected-state&iss=https%3A%2F%2Fother.test%2F",
            "error=access_denied&state=expected-state&iss=https%3A%2F%2Fother.test%2F",
            "code=secret-code&state=expected-state&iss=https%3A%2F%2Fidentity.test",
            "code=secret-code&state=expected-state&iss=%FF",
            "code=secret-code&state=expected-state&iss=%GG",
            "code=&state=expected-state",
            "code=secret-code",
        ] {
            assert_eq!(
                binding(false).validate(&target(query), host).unwrap_err(),
                CallbackError::InvalidResponse
            );
        }
        assert!(
            binding(true)
                .validate(&target("code=secret-code&state=expected-state"), host)
                .is_err()
        );
        assert!(
            binding(true)
                .validate(&target("error=access_denied&state=expected-state"), host)
                .is_err()
        );
        for wrong_host in [
            "localhost:52731",
            "127.0.0.1:52732",
            "127.0.0.1",
            "127.0.0.1:052731",
        ] {
            assert!(
                binding(false)
                    .validate(&target("code=c&state=expected-state"), wrong_host)
                    .is_err()
            );
        }
        for wrong_path in [
            "/oauth/callback",
            "/oauth/callback/other",
            "/oauth/callback/%66",
        ] {
            assert!(
                binding(false)
                    .validate(&format!("{wrong_path}?code=c&state=expected-state"), host)
                    .is_err()
            );
        }
    }

    #[test]
    fn full_supported_issuer_survives_worst_case_form_encoding_on_code_and_error() {
        let prefix = "https://identity.test/";
        let issuer = format!("{prefix}{}", "é".repeat((8192 - prefix.len()) / 2));
        let issuer = format!("{issuer}{}", "a".repeat(8192 - issuer.len()));
        assert_eq!(issuer.len(), 8192);
        let encoded = issuer
            .as_bytes()
            .iter()
            .fold(String::new(), |mut encoded, byte| {
                write!(&mut encoded, "%{byte:02X}").unwrap();
                encoded
            });
        assert_eq!(encoded.len(), 3 * 8192);
        let path = issuer_callback_path(&issuer);
        let pending = CallbackBinding::new(issuer, CsrfToken::new("state".into()), 52731, true);
        for result in ["code=protected-code", "error=access_denied"] {
            let target = format!("{path}?{result}&state=state&iss={encoded}");
            assert!(pending.validate(&target, "127.0.0.1:52731").is_ok());
        }
        let oversized = format!(
            "{path}?code={}&state=state&iss={encoded}",
            "x".repeat(REQUEST_TARGET_LIMIT)
        );
        assert!(pending.validate(&oversized, "127.0.0.1:52731").is_err());
    }
}
