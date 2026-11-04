//! Private loopback evidence does not qualify a browser or an OAuth provider.
#![allow(clippy::unwrap_used)]

use std::{fmt::Write as _, time::Duration};

use inframeld_cli::auth::callback::{CallbackListener, CallbackResponse};
use openidconnect::CsrfToken;
use tokio::io::AsyncWriteExt;

#[tokio::test]
async fn actual_ephemeral_listener_accepts_only_the_bound_transaction() {
    let callback = CallbackListener::bind("https://identity.test/".into())
        .await
        .unwrap();
    let uri = url::Url::parse(&callback.redirect_uri().unwrap()).unwrap();
    let host = format!("127.0.0.1:{}", uri.port().unwrap());
    let mut socket = tokio::net::TcpStream::connect(&host).await.unwrap();
    socket.write_all(format!("GET {}?code=protected-code&state=expected-state HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n", uri.path()).as_bytes()).await.unwrap();
    let result = callback
        .receive(
            CsrfToken::new("expected-state".into()),
            false,
            tokio::time::Instant::now() + Duration::from_secs(1),
        )
        .await;
    assert!(matches!(result, Ok(CallbackResponse::Code(_))));
    drop(socket);
    assert!(tokio::net::TcpStream::connect(&host).await.is_err());
}

async fn request(host: &str, target: &str, headers: &str) -> Option<u16> {
    use tokio::io::AsyncReadExt;
    let mut socket = tokio::net::TcpStream::connect(host).await.unwrap();
    let wire = format!("GET {target} HTTP/1.1\r\nHost: {host}\r\n{headers}\r\n");
    let _ = socket.write_all(wire.as_bytes()).await;
    let mut response = Vec::new();
    let _ = tokio::time::timeout(
        Duration::from_secs(1),
        socket.take(4096).read_to_end(&mut response),
    )
    .await
    .unwrap();
    std::str::from_utf8(&response)
        .ok()?
        .split_whitespace()
        .nth(1)?
        .parse()
        .ok()
}

fn address(callback: &CallbackListener) -> (String, String) {
    let uri = url::Url::parse(&callback.redirect_uri().unwrap()).unwrap();
    (
        format!("127.0.0.1:{}", uri.port().unwrap()),
        uri.path().to_owned(),
    )
}

#[tokio::test]
async fn seven_rejected_connections_leave_only_one_bound_callback_admission() {
    use inframeld_cli::auth::callback::issuer_callback_path;
    let callback = CallbackListener::bind("https://identity.test/".into())
        .await
        .unwrap();
    let (host, path) = address(&callback);
    let wrong_path = issuer_callback_path("https://other.test/");
    let queries = [
        format!("{path}?code=c&state=wrong"),
        format!("{path}?code=c&state=s&state=s"),
        format!("{path}?code=c&state=s&error=access_denied"),
        format!("{path}?code=c&state=s&iss=https%3A%2F%2Fother.test%2F"),
        format!("{path}?error=access_denied&state=s&iss=https%3A%2F%2Fother.test%2F"),
        format!("{wrong_path}?code=c&state=s"),
        format!("{wrong_path}?error=access_denied&state=s"),
    ];
    let (result, ()) = tokio::join!(
        callback.receive(
            CsrfToken::new("s".into()),
            false,
            tokio::time::Instant::now() + Duration::from_secs(3)
        ),
        async {
            for target in queries {
                assert_eq!(request(&host, &target, "").await, Some(400));
            }
            assert_eq!(
                request(&host, &format!("{path}?code=c&state=s"), "").await,
                Some(200)
            );
        }
    );
    assert!(matches!(result, Ok(CallbackResponse::Code(_))));
    assert!(tokio::net::TcpStream::connect(&host).await.is_err());
}

#[tokio::test]
async fn rejection_never_resets_the_total_connection_budget() {
    use inframeld_cli::auth::callback::CallbackError;
    let callback = CallbackListener::bind("https://identity.test/".into())
        .await
        .unwrap();
    let (host, path) = address(&callback);
    let (result, ()) = tokio::join!(
        callback.receive(
            CsrfToken::new("s".into()),
            false,
            tokio::time::Instant::now() + Duration::from_secs(3)
        ),
        async {
            for _ in 0..8 {
                assert_eq!(
                    request(&host, &format!("{path}?code=c&state=wrong"), "").await,
                    Some(400)
                );
            }
        }
    );
    assert_eq!(result.unwrap_err(), CallbackError::ConnectionLimit);
    assert!(tokio::net::TcpStream::connect(&host).await.is_err());
}

#[tokio::test]
async fn raw_header_target_count_and_body_budgets_do_not_consume_a_valid_callback() {
    let callback = CallbackListener::bind("https://identity.test/".into())
        .await
        .unwrap();
    let (host, path) = address(&callback);
    let (result, ()) = tokio::join!(
        callback.receive(
            CsrfToken::new("s".into()),
            false,
            tokio::time::Instant::now() + Duration::from_secs(3)
        ),
        async {
            let valid = format!("{path}?code=c&state=s");
            let headers = (0..33).fold(String::new(), |mut headers, index| {
                write!(&mut headers, "X-{index}: a\r\n").unwrap();
                headers
            });
            assert_ne!(request(&host, &valid, &headers).await, Some(200));
            let headers = format!("X-Padding:{}a\r\n", " ".repeat(32 * 1024));
            assert_ne!(request(&host, &valid, &headers).await, Some(200));
            assert_ne!(
                request(
                    &host,
                    &format!("{path}?code={}&state=s", "a".repeat(128 * 1024)),
                    ""
                )
                .await,
                Some(200)
            );
            assert_eq!(
                request(&host, &valid, "Content-Length: 1\r\n").await,
                Some(400)
            );
            assert_eq!(request(&host, &valid, "").await, Some(200));
        }
    );
    assert!(matches!(result, Ok(CallbackResponse::Code(_))));
}

#[tokio::test]
async fn full_issuer_expansion_reaches_the_real_parser_on_success_and_error() {
    let prefix = "https://identity.test/";
    let issuer = format!("{prefix}{}", "é".repeat((8192 - prefix.len()) / 2));
    let issuer = format!("{issuer}{}", "a".repeat(8192 - issuer.len()));
    let encoded = issuer
        .as_bytes()
        .iter()
        .fold(String::new(), |mut encoded, byte| {
            write!(&mut encoded, "%{byte:02X}").unwrap();
            encoded
        });
    assert_eq!(encoded.len(), 3 * 8192);
    for parameter in ["code=c", "error=access_denied"] {
        let callback = CallbackListener::bind(issuer.clone()).await.unwrap();
        let (host, path) = address(&callback);
        let target = format!("{path}?{parameter}&state=s&iss={encoded}");
        let (result, status) = tokio::join!(
            callback.receive(
                CsrfToken::new("s".into()),
                true,
                tokio::time::Instant::now() + Duration::from_secs(3)
            ),
            request(&host, &target, "")
        );
        assert_eq!(status, Some(200));
        assert!(result.is_ok());
    }
}

#[tokio::test]
async fn cancellation_closes_the_listener_and_stalled_connection_without_detached_tasks() {
    use tokio::io::AsyncReadExt;
    let callback = CallbackListener::bind("https://identity.test/".into())
        .await
        .unwrap();
    let (host, _) = address(&callback);
    let mut socket = tokio::net::TcpStream::connect(&host).await.unwrap();
    socket.write_all(b"GET ").await.unwrap();
    assert!(
        tokio::time::timeout(
            Duration::from_millis(30),
            callback.receive(
                CsrfToken::new("s".into()),
                false,
                tokio::time::Instant::now() + Duration::from_mins(1),
            )
        )
        .await
        .is_err()
    );
    let mut bytes = [0; 1];
    assert_eq!(
        tokio::time::timeout(Duration::from_secs(1), socket.read(&mut bytes))
            .await
            .unwrap()
            .unwrap(),
        0
    );
    assert!(tokio::net::TcpStream::connect(&host).await.is_err());
}

#[tokio::test]
async fn a_third_concurrent_connection_is_closed_and_still_spends_total_budget() {
    use tokio::io::AsyncReadExt;
    let callback = CallbackListener::bind("https://identity.test/".into())
        .await
        .unwrap();
    let (host, path) = address(&callback);
    let mut first = tokio::net::TcpStream::connect(&host).await.unwrap();
    let mut second = tokio::net::TcpStream::connect(&host).await.unwrap();
    first.write_all(b"GET ").await.unwrap();
    second.write_all(b"GET ").await.unwrap();
    let (result, ()) = tokio::join!(
        callback.receive(
            CsrfToken::new("s".into()),
            false,
            tokio::time::Instant::now() + Duration::from_secs(3)
        ),
        async {
            assert_eq!(
                request(&host, &format!("{path}?code=c&state=s"), "").await,
                None
            );
            for mut socket in [first, second] {
                socket
                    .write_all(
                        format!("{path}?code=c&state=wrong HTTP/1.1\r\nHost: {host}\r\n\r\n")
                            .as_bytes(),
                    )
                    .await
                    .unwrap();
                let mut response = Vec::new();
                tokio::time::timeout(
                    Duration::from_secs(1),
                    socket.take(4096).read_to_end(&mut response),
                )
                .await
                .unwrap()
                .unwrap();
                assert!(response.starts_with(b"HTTP/1.1 400"));
            }
            // Three accepted connections have already been spent, including the busy one.
            for _ in 0..4 {
                assert_eq!(
                    request(&host, &format!("{path}?code=c&state=wrong"), "").await,
                    Some(400)
                );
            }
            assert_eq!(
                request(&host, &format!("{path}?code=c&state=s"), "").await,
                Some(200)
            );
        }
    );
    assert!(matches!(result, Ok(CallbackResponse::Code(_))));
}
