//! Dropping an active generated call cancels it without poisoning client reuse.
#[cfg(test)]
mod tests {
    use std::io::{Read, Write};
    use std::net::TcpListener;
    use std::sync::mpsc;
    use std::time::Duration;

    #[tokio::test]
    async fn cancel_active_operation_and_reuse_client() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let address = listener.local_addr().unwrap();
        let (entered, started) = mpsc::channel();
        let server = std::thread::spawn(move || {
            for index in 0..2 {
                let (mut stream, _) = listener.accept().unwrap();
                stream
                    .set_read_timeout(Some(Duration::from_secs(2)))
                    .unwrap();
                read_request_headers(&mut stream).unwrap();
                if index == 0 {
                    entered.send(()).unwrap();
                    std::thread::sleep(Duration::from_millis(200));
                } else {
                    stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 15\r\nConnection: close\r\n\r\n{\"status\":\"ok\"}").unwrap();
                }
            }
        });
        let transport = reqwest::Client::builder()
            .no_proxy()
            .timeout(Duration::from_secs(2))
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .build()
            .unwrap();
        let client = inframeld_sdk::HttpClient::with_client(transport)
            .with_base_url(format!("http://{address}"));
        let active = client.clone();
        let task = tokio::spawn(async move { active.get_health().await });
        tokio::task::spawn_blocking(move || started.recv_timeout(Duration::from_secs(2)))
            .await
            .unwrap()
            .unwrap();
        task.abort();
        assert!(task.await.unwrap_err().is_cancelled());
        assert_eq!(client.get_health().await.unwrap().status, 200);
        drop(client);
        server.join().unwrap();
    }

    #[tokio::test]
    async fn encoded_paths_fail_before_opening_a_connection() {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        listener.set_nonblocking(true).unwrap();
        let client = inframeld_sdk::HttpClient::new()
            .with_base_url(format!("http://{}", listener.local_addr().unwrap()));
        for value in [
            "/absolute",
            "a?x=1",
            "a#fragment",
            "a\\b",
            "a%",
            "a%GG",
            "../admin",
            "a/%2e%2e/admin",
            "a%00b",
            "a%FF",
            "a b",
        ] {
            let result = client.get_protected_resource_metadata_for_path(value).await;
            assert!(
                matches!(
                    result,
                    Err(inframeld_sdk::client::ApiOpError::Transport(
                        inframeld_sdk::client::HttpError::Serialization(_)
                    ))
                ),
                "{value}: {result:?}"
            );
        }
        assert_eq!(
            listener.accept().unwrap_err().kind(),
            std::io::ErrorKind::WouldBlock
        );
    }

    fn read_request_headers(stream: &mut impl Read) -> std::io::Result<Vec<u8>> {
        let mut request = Vec::new();
        let mut buffer = [0; 4096];
        while !request.ends_with(b"\r\n\r\n") {
            let count = stream.read(&mut buffer)?;
            if count == 0 {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::UnexpectedEof,
                    "Incomplete probe request headers",
                ));
            }
            request.extend_from_slice(&buffer[..count]);
            if request.len() > 16384 {
                return Err(std::io::Error::new(
                    std::io::ErrorKind::InvalidData,
                    "Probe request headers exceed the test bound",
                ));
            }
        }
        Ok(request)
    }

    #[test]
    fn probe_reads_complete_headers_before_replying() {
        let request = format!(
            "GET /health HTTP/1.1\r\nX-Probe: {}\r\n\r\n",
            "a".repeat(5000)
        );
        let mut fragmented = std::io::Cursor::new(request.as_bytes());
        assert_eq!(
            read_request_headers(&mut fragmented).unwrap(),
            request.as_bytes()
        );
    }

    struct Probe {
        url: String,
        count: std::sync::Arc<std::sync::atomic::AtomicUsize>,
        stop: std::sync::Arc<std::sync::atomic::AtomicBool>,
        thread: Option<std::thread::JoinHandle<()>>,
    }

    impl Probe {
        fn start(handler: fn(&mut std::net::TcpStream, usize)) -> Self {
            use std::sync::{
                Arc,
                atomic::{AtomicBool, AtomicUsize, Ordering},
            };
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            listener.set_nonblocking(true).unwrap();
            let url = format!("http://{}", listener.local_addr().unwrap());
            let count = Arc::new(AtomicUsize::new(0));
            let stop = Arc::new(AtomicBool::new(false));
            let seen = count.clone();
            let finished = stop.clone();
            let thread = std::thread::spawn(move || {
                while !finished.load(Ordering::SeqCst) {
                    match listener.accept() {
                        Ok((mut stream, _)) => {
                            // Accept polling is nonblocking, but header reads must wait for bytes.
                            stream.set_nonblocking(false).unwrap();
                            stream
                                .set_read_timeout(Some(Duration::from_secs(1)))
                                .unwrap();
                            if read_request_headers(&mut stream).is_ok() {
                                let index = seen.fetch_add(1, Ordering::SeqCst);
                                handler(&mut stream, index);
                                // Send an orderly EOF, then consume any remaining request bytes
                                // before closing so macOS cannot reset an unread socket.
                                let _ = stream.shutdown(std::net::Shutdown::Write);
                                let _ = std::io::copy(&mut stream, &mut std::io::sink());
                            }
                        }
                        Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                            std::thread::sleep(Duration::from_millis(5))
                        }
                        Err(error) => panic!("Probe accept failed: {error}"),
                    }
                }
            });
            Self {
                url,
                count,
                stop,
                thread: Some(thread),
            }
        }
    }

    impl Drop for Probe {
        fn drop(&mut self) {
            self.stop.store(true, std::sync::atomic::Ordering::SeqCst);
            self.thread.take().unwrap().join().unwrap();
        }
    }

    fn slow_body(stream: &mut std::net::TcpStream, _index: usize) {
        if stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 10000\r\nConnection: close\r\n\r\n").is_err() { return; }
        for _ in 0..60 {
            if stream.write_all(b" ").is_err() {
                return;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
    }

    #[tokio::test]
    async fn default_constructor_bounds_buffered_body_without_redispatch() {
        let probe = Probe::start(slow_body);
        let client = inframeld_sdk::HttpClient::new().with_base_url(&probe.url);
        let started = std::time::Instant::now();
        let result = client.get_health().await;
        assert!(result.is_err(), "Expected deadline failure: {result:?}");
        assert!(
            started.elapsed() >= Duration::from_millis(4500),
            "Unexpected early failure: {result:?}"
        );
        assert!(
            started.elapsed() < Duration::from_millis(5800),
            "Configured deadline was not applied"
        );
        assert_eq!(probe.count.load(std::sync::atomic::Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn default_constructor_does_not_follow_redirects() {
        let probe = Probe::start(|stream, index| {
            if index == 0 {
                stream.write_all(b"HTTP/1.1 307 Temporary Redirect\r\nLocation: /target\r\nContent-Length: 0\r\nConnection: close\r\n\r\n").unwrap();
            } else {
                stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: 15\r\nConnection: close\r\n\r\n{\"status\":\"ok\"}").unwrap();
            }
        });
        let result = inframeld_sdk::HttpClient::new()
            .with_base_url(&probe.url)
            .get_health()
            .await;
        let error = result.unwrap_err();
        assert_eq!(
            error
                .api()
                .expect(&format!("Expected HTTP context: {error:?}"))
                .status,
            307
        );
        assert_eq!(probe.count.load(std::sync::atomic::Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn caller_supplied_transport_keeps_its_deadline() {
        let probe = Probe::start(slow_body);
        let transport = reqwest::Client::builder()
            .timeout(Duration::from_millis(40))
            .no_proxy()
            .build()
            .unwrap();
        let client = inframeld_sdk::HttpClient::with_client(transport).with_base_url(&probe.url);
        let started = std::time::Instant::now();
        assert!(client.get_health().await.is_err());
        assert!(started.elapsed() < Duration::from_millis(500));
    }
}
