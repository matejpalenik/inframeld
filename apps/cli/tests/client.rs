// Disposable server setup and assertions fail immediately rather than hiding a failed fixture.
#![allow(clippy::unwrap_used)]
use inframeld_cli::{client, context::Connection};
use std::{
    io::{Read, Write},
    net::TcpListener,
    thread,
    time::Duration,
};

#[tokio::test]
async fn generated_health_request_preserves_metadata_and_does_not_redispatch() {
    for (status, body) in [
        ("200 OK", r#"{"status":"ok"}"#),
        ("503 Unavailable", "{}"),
        ("302 Found", "{}"),
        ("200 OK", "invalid"),
    ] {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        let server = thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream
                .set_read_timeout(Some(Duration::from_secs(2)))
                .unwrap();
            let mut request = [0; 8192];
            let length = stream.read(&mut request).unwrap();
            assert!(
                String::from_utf8_lossy(&request[..length]).starts_with("GET /health HTTP/1.1")
            );
            write!(stream, "HTTP/1.1 {status}\r\nContent-Type: application/json\r\nX-Request-Id: test-request\r\nLocation: /redirected\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len()).unwrap();
            drop(stream);
            listener.set_nonblocking(true).unwrap();
            thread::sleep(Duration::from_millis(150));
            assert!(listener.accept().is_err(), "SDK must not redispatch");
        });
        let sdk = client::connect(&Connection::new(&base).unwrap());
        let result = sdk.get_health().await;
        if body.contains("ok") {
            let response = result.unwrap();
            assert_eq!(response.status, 200);
            assert_eq!(response.headers["x-request-id"], "test-request");
        } else {
            let error = result.unwrap_err();
            let api = error.api().unwrap();
            assert_eq!(api.headers["x-request-id"], "test-request");
            assert_eq!(api.raw_body, body.as_bytes());
        }
        server.join().unwrap();
    }
}

#[tokio::test]
async fn unavailable_server_is_a_transport_failure_without_fabricated_http_metadata() {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let connection =
        Connection::new(&format!("http://{}", listener.local_addr().unwrap())).unwrap();
    drop(listener);
    let error = client::connect(&connection).get_health().await.unwrap_err();
    assert!(error.api().is_none());
}

#[test]
fn explicit_connections_reject_ambiguous_or_secret_inputs() {
    for input in ["http://localhost:8000/", "https://example.com/api/"] {
        assert!(Connection::new(input).is_ok());
    }
    for input in [
        "bad",
        "ftp://example.com",
        "https://user:secret@example.com",
        "https://example.com?key=secret",
        "https://example.com#fragment",
    ] {
        assert!(Connection::new(input).is_err());
    }
}
