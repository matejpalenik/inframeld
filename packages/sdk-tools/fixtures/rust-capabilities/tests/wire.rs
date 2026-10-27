//! Synthetic wire evidence for generator fixes, independent of product workflows.
use futures_util::StreamExt;
use inframeld_sdk_test_rust_capabilities::{HttpClient, types::MultipartFile};
use std::{
    io::{Read, Write},
    net::TcpListener,
    sync::mpsc,
    thread,
    time::Duration,
};

struct Server {
    url: String,
    release: Option<mpsc::Sender<()>>,
    request: thread::JoinHandle<Vec<u8>>,
}

impl Server {
    fn finish(mut self) -> Vec<u8> {
        if let Some(release) = self.release.take() {
            let _ = release.send(());
        }
        self.request.join().unwrap()
    }
}

fn server(status: u16, content_type: &str, body: &[u8], hold_body: bool) -> Server {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let body = body.to_vec();
    let content_type = content_type.to_owned();
    let (release, wait) = mpsc::channel();
    let request = thread::spawn(move || {
        let (mut socket, _) = listener.accept().unwrap();
        socket
            .set_read_timeout(Some(Duration::from_secs(5)))
            .unwrap();
        let mut request = Vec::new();
        let mut chunk = [0; 4096];
        let header_end = loop {
            let count = socket.read(&mut chunk).unwrap();
            assert!(count > 0, "request ended before its headers");
            request.extend_from_slice(&chunk[..count]);
            if let Some(end) = request.windows(4).position(|w| w == b"\r\n\r\n") {
                break end + 4;
            }
        };
        let headers = String::from_utf8_lossy(&request[..header_end]).to_ascii_lowercase();
        let length = headers
            .lines()
            .find_map(|line| line.strip_prefix("content-length: "))
            .map(|value| value.trim().parse::<usize>().unwrap());
        while length.is_some_and(|length| request.len() < header_end + length)
            || headers.contains("transfer-encoding: chunked") && !request.ends_with(b"0\r\n\r\n")
        {
            let count = socket.read(&mut chunk).unwrap();
            assert!(count > 0, "request ended before its body");
            request.extend_from_slice(&chunk[..count]);
        }
        write!(socket, "HTTP/1.1 {status} Test\r\nContent-Type: {content_type}\r\nContent-Length: {}\r\nX-Request-ID: patch-request\r\nSet-Cookie: first=1\r\nSet-Cookie: second=2\r\nConnection: close\r\n\r\n", body.len()).unwrap();
        socket.flush().unwrap();
        if hold_body {
            wait.recv_timeout(Duration::from_secs(5)).unwrap();
        }
        socket.write_all(&body).unwrap();
        request
    });
    Server {
        url,
        release: Some(release),
        request,
    }
}

fn client(base: &str) -> HttpClient {
    let transport = reqwest::Client::builder()
        .no_proxy()
        .redirect(reqwest::redirect::Policy::none())
        .retry(reqwest::retry::never())
        .timeout(Duration::from_secs(3))
        .build()
        .unwrap();
    HttpClient::with_client(transport).with_base_url(base)
}

#[tokio::test]
async fn json_keeps_typed_body_status_and_repeated_headers() {
    let server = server(200, "application/json", br#"{"value":"example"}"#, false);
    let response = client(&server.url).get_json().await.unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    assert_eq!(response.headers.get_all("set-cookie").iter().count(), 2);
    let mapped = response.map_body(|body| body.value);
    assert_eq!(mapped.body, "example");
    assert_eq!(mapped.headers["x-request-id"], "patch-request");
    assert!(server.finish().starts_with(b"GET /json "));
}

#[tokio::test]
async fn text_keeps_its_body_and_metadata() {
    let server = server(200, "text/plain", b"example", false);
    let response = client(&server.url).get_text().await.unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    assert_eq!(response.body, "example");
    server.finish();
}

#[tokio::test]
async fn empty_success_keeps_204_and_metadata() {
    let server = server(204, "application/octet-stream", b"", false);
    let response = client(&server.url).get_empty().await.unwrap();
    assert_eq!(response.status, 204);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    let (): () = response.body;
    server.finish();
}

#[tokio::test]
async fn binary_keeps_exact_bytes_and_metadata() {
    let server = server(200, "application/octet-stream", b"\0binary\xff", false);
    let response = client(&server.url).get_binary().await.unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    assert_eq!(response.body.as_ref(), b"\0binary\xff");
    server.finish();
}

#[tokio::test]
async fn raw_events_return_metadata_before_the_live_body_arrives() {
    let mut server = server(200, "text/event-stream", b"data: example\n\n", true);
    let response = tokio::time::timeout(Duration::from_secs(1), client(&server.url).get_events())
        .await
        .unwrap()
        .unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    server.release.take().unwrap().send(()).unwrap();
    let bytes = response
        .body
        .collect::<Vec<_>>()
        .await
        .into_iter()
        .flat_map(Result::unwrap)
        .collect::<Vec<_>>();
    assert_eq!(bytes, b"data: example\n\n");
    server.finish();
}

#[tokio::test]
async fn parsed_events_keep_metadata_and_event_data() {
    let mut server = server(200, "text/event-stream", b"data: example\n\n", true);
    let response =
        tokio::time::timeout(Duration::from_secs(1), client(&server.url).get_events_sse())
            .await
            .unwrap()
            .unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    server.release.take().unwrap().send(()).unwrap();
    let events = response.body.collect::<Vec<_>>().await;
    assert_eq!(events.len(), 1);
    assert_eq!(events[0].as_ref().unwrap().data, "example");
    server.finish();
}

#[tokio::test]
async fn binary_stream_keeps_metadata_without_buffering() {
    let mut server = server(200, "application/octet-stream", b"\0binary\xff", true);
    let response = tokio::time::timeout(
        Duration::from_secs(1),
        client(&server.url).get_binary_binary_stream(),
    )
    .await
    .unwrap()
    .unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    server.release.take().unwrap().send(()).unwrap();
    let bytes = response
        .body
        .collect::<Vec<_>>()
        .await
        .into_iter()
        .flat_map(Result::unwrap)
        .collect::<Vec<_>>();
    assert_eq!(bytes, b"\0binary\xff");
    server.finish();
}

#[tokio::test]
async fn malformed_success_stays_an_inspectable_failure() {
    let server = server(200, "application/json", b"{", false);
    let error = client(&server.url).get_json().await.unwrap_err();
    let api = error.api().unwrap();
    assert_eq!(api.status, 200);
    assert_eq!(api.headers["x-request-id"], "patch-request");
    assert_eq!(api.raw_body, b"{");
    assert!(api.parse_error.is_some());
    server.finish();
}

#[tokio::test]
async fn unexpected_status_keeps_its_raw_body_and_metadata() {
    let server = server(418, "text/plain", b"unexpected", false);
    let error = client(&server.url).get_json().await.unwrap_err();
    let api = error.api().unwrap();
    assert_eq!(api.status, 418);
    assert_eq!(api.headers["x-request-id"], "patch-request");
    assert_eq!(api.raw_body, b"unexpected");
    server.finish();
}

#[tokio::test]
async fn multipart_builder_sends_files_and_keeps_text_fields_as_text() {
    let server = server(204, "application/octet-stream", b"", false);
    let file = |name: &str| MultipartFile::from(Vec::from(&b"\0part\xff"[..])).with_file_name(name);
    let response = client(&server.url)
        .upload_variants_builder("YWJj".into(), file("required.bin"), "label".into())
        .files(vec![file("array.bin")])
        .optional_file(file("optional.bin"))
        .send()
        .await
        .unwrap();
    assert_eq!(response.status, 204);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    let request = server.finish();
    let text = String::from_utf8_lossy(&request);
    for name in ["required.bin", "array.bin", "optional.bin"] {
        assert!(
            text.contains(&format!("filename=\"{name}\"")),
            "missing {name}"
        );
    }
    assert_eq!(
        request.windows(6).filter(|w| *w == b"\0part\xff").count(),
        3
    );
    assert!(text.contains("name=\"encoded\"\r\n\r\nYWJj"));
    assert!(text.contains("name=\"label\"\r\n\r\nlabel"));
}

#[tokio::test]
async fn json_operation_builder_preserves_metadata_and_query_encoding() {
    let server = server(200, "application/json", br#"{"value":"builder"}"#, false);
    let response = client(&server.url)
        .get_builder_json_builder()
        .tag("a b&")
        .send()
        .await
        .unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    assert_eq!(response.body.value, "builder");
    assert!(
        server
            .finish()
            .starts_with(b"GET /builder-json?tag=a+b%26 ")
    );
}

#[tokio::test]
async fn raw_stream_builder_preserves_metadata_with_a_concrete_request_media_type() {
    let mut server = server(200, "text/event-stream", b"data: builder\n\n", true);
    let http = client(&server.url);
    let response = tokio::time::timeout(
        Duration::from_secs(1),
        http.stream_events_builder()
            .body(vec![0, 255])
            .content_type("application/octet-stream")
            .send(),
    )
    .await
    .unwrap()
    .unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    server.release.take().unwrap().send(()).unwrap();
    let bytes = response
        .body
        .collect::<Vec<_>>()
        .await
        .into_iter()
        .flat_map(Result::unwrap)
        .collect::<Vec<_>>();
    assert_eq!(bytes, b"data: builder\n\n");
    let request = server.finish();
    assert!(request.ends_with(&[0, 255]));
}

#[tokio::test]
async fn parsed_stream_builder_preserves_metadata_and_events() {
    let mut server = server(200, "text/event-stream", b"data: builder\n\n", true);
    let http = client(&server.url);
    let response = tokio::time::timeout(
        Duration::from_secs(1),
        http.stream_events_sse_builder()
            .body(vec![0, 255])
            .content_type("application/octet-stream")
            .send(),
    )
    .await
    .unwrap()
    .unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    server.release.take().unwrap().send(()).unwrap();
    let events = response.body.collect::<Vec<_>>().await;
    assert_eq!(events[0].as_ref().unwrap().data, "builder");
    assert!(server.finish().ends_with(&[0, 255]));
}

#[tokio::test]
async fn raw_stream_builder_without_a_body_preserves_metadata() {
    let mut server = server(200, "text/event-stream", b"data: empty request\n\n", true);
    let http = client(&server.url);
    let response =
        tokio::time::timeout(Duration::from_secs(1), http.stream_events_builder().send())
            .await
            .unwrap()
            .unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(response.headers["x-request-id"], "patch-request");
    server.release.take().unwrap().send(()).unwrap();
    let bytes = response
        .body
        .collect::<Vec<_>>()
        .await
        .into_iter()
        .flat_map(Result::unwrap)
        .collect::<Vec<_>>();
    assert_eq!(bytes, b"data: empty request\n\n");
    server.finish();
}

#[tokio::test]
async fn default_only_json_keeps_its_typed_body() {
    let server = server(200, "application/json", br#"{"value":"example"}"#, false);
    let response = client(&server.url).get_default_only().await.unwrap();
    assert_eq!(response.status, 200);
    assert_eq!(
        serde_json::to_value(response.body).unwrap(),
        serde_json::json!({"value":"example"})
    );
    server.finish();
}

#[tokio::test]
async fn default_only_json_rejects_malformed_bodies() {
    let server = server(200, "application/json", b"null", false);
    let error = client(&server.url).get_default_only().await.unwrap_err();
    assert_eq!(error.api().unwrap().status, 200);
    assert!(error.api().unwrap().parse_error.is_some());
    server.finish();
}
