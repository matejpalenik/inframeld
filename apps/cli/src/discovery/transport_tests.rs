#![allow(clippy::unwrap_used, clippy::expect_used)]
use super::{
    BODY_LIMIT, DiscoveryError, DiscoveryOptions, ManagedLocalContext, discover,
    discover::discover_with_budget, discover_with_context, url_policy::UrlPolicy,
};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::{
    io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt},
    net::TcpListener,
    task::{JoinHandle, JoinSet},
};
use tokio_rustls::TlsAcceptor;
use url::Url;
use uuid::Uuid;

#[derive(Clone, Copy, Debug)]
enum Fault {
    None,
    Redirect,
    ProviderRedirect,
    KeysRedirect,
    KeysOversized,
    Resource,
    Version,
    Oversized,
    Malformed,
    Issuer,
    Keys,
    Token,
    Pkce,
    Slow,
    GrantMissing,
    GrantNoRefresh,
    GrantClient,
}
struct Server {
    base: String,
    issuer: String,
    ca: reqwest::Certificate,
    requests: Arc<Mutex<Vec<String>>>,
    task: JoinHandle<()>,
}
impl Drop for Server {
    fn drop(&mut self) {
        self.task.abort();
    }
}

async fn serve(
    mut socket: impl AsyncRead + AsyncWrite + Unpin,
    base: &str,
    path: &str,
    fault: Fault,
    requests: &Mutex<Vec<String>>,
    issuer: &str,
) {
    let mut bytes = vec![];
    while !bytes.ends_with(b"\r\n\r\n") {
        let mut byte = [0];
        if socket.read_exact(&mut byte).await.is_err() {
            return;
        }
        bytes.push(byte[0]);
        assert!(bytes.len() < 32 * 1024);
    }
    let request = String::from_utf8(bytes).unwrap();
    let target = request.split_whitespace().nth(1).unwrap();
    let target = if target.starts_with("http:") {
        Url::parse(target).unwrap().path().to_owned()
    } else {
        target.to_owned()
    };
    requests.lock().unwrap().push(request);
    let routing_url = Url::parse(&format!("{base}{path}")).unwrap();
    let suffix = if path.is_empty() || path == "/" {
        ""
    } else {
        routing_url.path()
    };
    let issuer_url = Url::parse(issuer).unwrap();
    let provider_path = issuer_url.path().trim_end_matches('/');
    let endpoint_base = format!("{}/", issuer.trim_end_matches('/'));
    let (status, body) = if target == format!("/.well-known/oauth-protected-resource{suffix}") {
        match fault {
            Fault::Redirect => (302, "{}".into()),
            Fault::Oversized => (200, "x".repeat(BODY_LIMIT + 1)),
            Fault::Slow => { tokio::time::sleep(Duration::from_mins(1)).await; (200, "{}".into()) },
            _ => (200, serde_json::json!({"resource": if matches!(fault, Fault::Resource) {format!("{base}/other")} else {format!("{base}{path}")}, "authorization_servers": [issuer], "scopes_supported": ["inframeld:api"], "bearer_methods_supported": ["header"], "inframeld": {"installation_id": Uuid::from_u128(1), "client_id": "inframeld-cli", "schema_version": if matches!(fault, Fault::Version) {2} else {1}}}).to_string()),
        }
    } else if target == format!("{provider_path}/.well-known/openid-configuration") {
        if matches!(fault, Fault::ProviderRedirect) {
            (302, "{}".into())
        } else if matches!(fault, Fault::Malformed) {
            (200, "private invalid body".into())
        } else {
            let mut metadata = serde_json::json!({
                "issuer": if matches!(fault, Fault::Issuer) {format!("{base}/wrong/")} else {issuer.to_owned()},
                "authorization_endpoint": format!("{endpoint_base}authorize"),
                "token_endpoint": if matches!(fault, Fault::Token) {"https://foreign.test/token".into()} else {format!("{endpoint_base}token")},
                "jwks_uri": if matches!(fault, Fault::Keys) {"https://foreign.test/keys".into()} else {format!("{endpoint_base}keys")},
                "userinfo_endpoint": format!("{endpoint_base}userinfo"),
                "revocation_endpoint": format!("{endpoint_base}revoke"),
                "grant_types_supported": match fault {
                    Fault::GrantClient => Some(vec!["client_credentials"]),
                    Fault::GrantNoRefresh => Some(vec!["authorization_code"]),
                    Fault::GrantMissing => None,
                    _ => Some(vec!["authorization_code", "refresh_token"]),
                },
                "response_types_supported": ["code"],
                "token_endpoint_auth_methods_supported": ["none"],
                "subject_types_supported": ["public"],
                "id_token_signing_alg_values_supported": ["RS256"],
                "code_challenge_methods_supported": if matches!(fault, Fault::Pkce) {vec!["plain"]} else {vec!["S256"]},
            });
            if matches!(fault, Fault::GrantMissing) {
                metadata
                    .as_object_mut()
                    .unwrap()
                    .remove("grant_types_supported");
            }
            (200, metadata.to_string())
        }
    } else if target != format!("{provider_path}/keys") {
        (404, "{}".into())
    } else if matches!(fault, Fault::KeysRedirect) {
        (302, "{}".into())
    } else if matches!(fault, Fault::KeysOversized) {
        (200, "x".repeat(BODY_LIMIT + 1))
    } else {
        // Synthetic public key material. These tests do not perform authentication.
        (200, r#"{"keys":[{"kty":"RSA","kid":"test","use":"sig","alg":"RS256","n":"AQAB","e":"AQAB"}]}"#.into())
    };
    let response = format!(
        "HTTP/1.1 {status} Test\r\nContent-Type: application/json\r\nContent-Length: {}\r\nLocation: https://foreign.test/\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = socket.write_all(response.as_bytes()).await;
    let _ = socket.shutdown().await;
}

async fn server(tls: bool, path: &str, fault: Fault, wrong_host: bool, expired: bool) -> Server {
    server_with_issuer(tls, path, fault, wrong_host, expired, |base| {
        format!("{base}/issuer/")
    })
    .await
}

/// Resolve issuer spelling after the fixture's ephemeral listening address is known.
async fn server_with_issuer(
    tls: bool,
    path: &str,
    fault: Fault,
    wrong_host: bool,
    expired: bool,
    issuer: impl FnOnce(&str) -> String,
) -> Server {
    let _ = rustls::crypto::ring::default_provider().install_default();
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let base = format!(
        "{}://{}",
        if tls { "https" } else { "http" },
        listener.local_addr().unwrap()
    );
    let issuer = issuer(&base);
    let mut params = rcgen::CertificateParams::new(vec![if wrong_host {
        "wrong.test".into()
    } else {
        "127.0.0.1".into()
    }])
    .unwrap();
    if expired {
        params.not_before = rcgen::date_time_ymd(2019, 1, 1);
        params.not_after = rcgen::date_time_ymd(2020, 1, 1);
    }
    let key = rcgen::KeyPair::generate().unwrap();
    let cert = params.self_signed(&key).unwrap();
    let ca = reqwest::Certificate::from_der(cert.der()).unwrap();
    let config = rustls::ServerConfig::builder_with_provider(Arc::new(
        rustls::crypto::ring::default_provider(),
    ))
    .with_safe_default_protocol_versions()
    .unwrap()
    .with_no_client_auth()
    .with_single_cert(
        vec![cert.der().clone()],
        rustls::pki_types::PrivatePkcs8KeyDer::from(key.serialize_der()).into(),
    )
    .unwrap();
    let acceptor = TlsAcceptor::from(Arc::new(config));
    let requests = Arc::new(Mutex::new(vec![]));
    let (server_base, records, path) = (base.clone(), requests.clone(), path.to_owned());
    let server_issuer = issuer.clone();
    let task = tokio::spawn(async move {
        let mut children = JoinSet::new();
        loop {
            tokio::select! {
                connection = listener.accept() => {
                    let (socket, _) = connection.unwrap();
                    let (base, records, path, acceptor, issuer) = (server_base.clone(), records.clone(), path.clone(), acceptor.clone(), server_issuer.clone());
                    children.spawn(async move {
                        if tls { if let Ok(socket) = acceptor.accept(socket).await {serve(socket, &base, &path, fault, &records, &issuer).await;} }
                        else { serve(socket, &base, &path, fault, &records, &issuer).await; }
                    });
                },
                result = children.join_next(), if !children.is_empty() => { result.unwrap().unwrap(); }
            }
        }
    });
    Server {
        base,
        issuer,
        ca,
        requests,
        task,
    }
}

fn context(server: &Server) -> ManagedLocalContext {
    let origin = Url::parse(&server.base).unwrap().origin();
    ManagedLocalContext {
        installation_id: Uuid::from_u128(1),
        api_origin: origin.clone(),
        issuer_origin: origin,
    }
}

#[tokio::test]
async fn verified_https_supports_root_and_prefixed_resources_without_credentials() {
    for path in ["", "/", "/api/v1", "/api/", "/a%20b", "/api%2Fv1"] {
        let server = server(true, path, Fault::None, false, false).await;
        let result = discover(
            &format!("{}{path}", server.base),
            DiscoveryOptions {
                certificate_authorities: vec![server.ca.clone()],
                proxy: None,
            },
        )
        .await
        .unwrap();
        assert_eq!(result.resource, format!("{}{path}", server.base));
        assert_eq!(result.installation_id, Uuid::from_u128(1));
        let requests = server.requests.lock().unwrap();
        assert_eq!(requests.len(), 3);
        let suffix = if path == "/" { "" } else { path };
        assert!(
            requests[0].starts_with(&format!(
                "GET /.well-known/oauth-protected-resource{suffix} "
            )),
            "{}",
            requests[0]
        );
        for request in requests.iter() {
            assert!(!request.to_lowercase().contains("authorization:"));
            assert!(!request.to_lowercase().contains("cookie:"));
        }
    }
}

#[tokio::test]
async fn unicode_identity_survives_encoded_path_expansion() {
    let path = format!("/{}", "é".repeat(1500));
    let server = server(true, &path, Fault::None, false, false).await;
    let identity = format!("{}{path}", server.base);
    assert!(identity.len() < 8192);
    let result = discover(
        &identity,
        DiscoveryOptions {
            certificate_authorities: vec![server.ca.clone()],
            proxy: None,
        },
    )
    .await
    .unwrap();
    assert_eq!(result.resource, identity);
    let requests = server.requests.lock().unwrap();
    assert_eq!(requests.len(), 3);
    assert!(requests[0].starts_with(&format!(
        "GET /.well-known/oauth-protected-resource/{} ",
        "%C3%A9".repeat(1500)
    )));
    for request in requests.iter() {
        assert!(!request.to_lowercase().contains("authorization:"));
        assert!(!request.to_lowercase().contains("cookie:"));
    }
}

#[tokio::test]
async fn unicode_issuer_and_endpoints_survive_encoded_path_expansion() {
    let server = server_with_issuer(true, "", Fault::None, false, false, |base| {
        format!("{base}/{}/", "é".repeat(1500))
    })
    .await;
    assert!(server.issuer.len() < 8192);
    let result = discover(
        &server.base,
        DiscoveryOptions {
            certificate_authorities: vec![server.ca.clone()],
            proxy: None,
        },
    )
    .await
    .unwrap();
    assert_eq!(result.provider.issuer().as_str(), server.issuer);
    for endpoint in [
        result.provider.authorization_endpoint().url(),
        result.provider.token_endpoint().unwrap().url(),
        result.provider.jwks_uri().url(),
        result.provider.userinfo_endpoint().unwrap().url(),
        result
            .provider
            .additional_metadata()
            .revocation_endpoint
            .as_ref()
            .unwrap(),
    ] {
        assert!(endpoint.as_str().len() > 8192);
    }
    let requests = server.requests.lock().unwrap();
    assert_eq!(requests.len(), 3);
    let encoded = "%C3%A9".repeat(1500);
    assert!(requests[1].starts_with(&format!("GET /{encoded}/.well-known/openid-configuration ")));
    assert!(requests[2].starts_with(&format!("GET /{encoded}/keys ")));
    for request in requests.iter() {
        assert!(!request.to_lowercase().contains("authorization:"));
        assert!(!request.to_lowercase().contains("cookie:"));
    }
}

#[tokio::test]
async fn original_issuer_budget_is_independent_of_derived_requests() {
    for size in [8192, 8193] {
        let server = server_with_issuer(true, "", Fault::None, false, false, |base| {
            format!("{base}/{}", "a".repeat(size - base.len() - 1))
        })
        .await;
        assert_eq!(server.issuer.len(), size);
        assert!(!server.issuer.ends_with('/'));
        let result = discover(
            &server.base,
            DiscoveryOptions {
                certificate_authorities: vec![server.ca.clone()],
                proxy: None,
            },
        )
        .await;
        if size == 8192 {
            assert_eq!(result.unwrap().provider.issuer().as_str(), server.issuer);
            let requests = server.requests.lock().unwrap();
            assert_eq!(requests.len(), 3);
            let path = format!("/{}", "a".repeat(size - server.base.len() - 1));
            assert!(
                requests[1].starts_with(&format!("GET {path}/.well-known/openid-configuration "))
            );
        } else {
            assert_eq!(result.unwrap_err(), DiscoveryError::InvalidUrl);
            assert_eq!(server.requests.lock().unwrap().len(), 1);
        }
    }
}

#[tokio::test]
async fn encoded_provider_budget_rejects_before_dispatch() {
    use openidconnect::AsyncHttpClient as _;

    let server = server(true, "", Fault::None, false, false).await;
    let client = super::oidc_transport::client(
        DiscoveryOptions {
            certificate_authorities: vec![server.ca.clone()],
            proxy: None,
        },
        Duration::from_secs(2),
    )
    .unwrap();
    let transport = super::oidc_transport::OidcTransport::new(
        client,
        Url::parse(&server.base).unwrap().origin(),
        UrlPolicy::new(None),
    );
    for (size, expected) in [
        (24609, DiscoveryError::Unavailable),
        (24610, DiscoveryError::InvalidUrl),
    ] {
        let target = format!(
            "{}/{}",
            server.base,
            "a".repeat(size - server.base.len() - 1)
        );
        assert_eq!(target.len(), size);
        let request = http::Request::builder()
            .uri(target)
            .body(Vec::new())
            .unwrap();
        assert_eq!(transport.call(request).await.unwrap_err(), expected);
    }
    assert_eq!(server.requests.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn refused_connection_remains_a_transport_failure() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let identity = format!("https://{}", listener.local_addr().unwrap());
    drop(listener);
    assert_eq!(
        discover(&identity, DiscoveryOptions::default())
            .await
            .unwrap_err(),
        DiscoveryError::Transport
    );
}

#[tokio::test]
async fn unsafe_metadata_remains_failure_without_a_second_origin_request() {
    for (fault, expected) in [
        (Fault::Redirect, DiscoveryError::Redirect),
        (Fault::ProviderRedirect, DiscoveryError::Redirect),
        (Fault::KeysRedirect, DiscoveryError::Redirect),
        (Fault::KeysOversized, DiscoveryError::ResponseTooLarge),
        (Fault::Resource, DiscoveryError::IdentityMismatch),
        (Fault::Version, DiscoveryError::UnsupportedProfile),
        (Fault::Oversized, DiscoveryError::ResponseTooLarge),
        (Fault::Malformed, DiscoveryError::InvalidMetadata),
        (Fault::Issuer, DiscoveryError::IdentityMismatch),
        (Fault::Keys, DiscoveryError::IdentityMismatch),
        (Fault::Token, DiscoveryError::IdentityMismatch),
        (Fault::Pkce, DiscoveryError::UnsupportedProfile),
        (Fault::GrantMissing, DiscoveryError::UnsupportedProfile),
        (Fault::GrantNoRefresh, DiscoveryError::UnsupportedProfile),
        (Fault::GrantClient, DiscoveryError::UnsupportedProfile),
    ] {
        let server = server(false, "", fault, false, false).await;
        let error = discover_with_context(
            &server.base,
            DiscoveryOptions::default(),
            Some(&context(&server)),
        )
        .await
        .unwrap_err();
        assert_eq!(error, expected, "{fault:?}");
        assert!(!error.to_string().contains("private"));
        assert!(server.requests.lock().unwrap().len() <= 3);
    }
}

#[tokio::test]
async fn tls_rejects_untrusted_wrong_host_and_expired_certificates() {
    for (wrong_host, expired, trusted) in [
        (false, false, false),
        (true, false, true),
        (false, true, true),
    ] {
        let server = server(true, "", Fault::None, wrong_host, expired).await;
        let options = DiscoveryOptions {
            certificate_authorities: if trusted {
                vec![server.ca.clone()]
            } else {
                vec![]
            },
            proxy: None,
        };
        assert_eq!(
            discover(&server.base, options).await.unwrap_err(),
            DiscoveryError::Tls
        );
        assert!(server.requests.lock().unwrap().is_empty());
    }
}

#[tokio::test]
async fn managed_loopback_rejects_manual_http_and_explicit_proxy() {
    let server = server(false, "", Fault::None, false, false).await;
    assert_eq!(
        discover(&server.base, DiscoveryOptions::default())
            .await
            .unwrap_err(),
        DiscoveryError::InvalidUrl
    );
    assert!(server.requests.lock().unwrap().is_empty());
    let options = DiscoveryOptions {
        proxy: Some(reqwest::Proxy::all(&server.base).unwrap()),
        ..DiscoveryOptions::default()
    };
    assert_eq!(
        discover_with_context(&server.base, options, Some(&context(&server)))
            .await
            .unwrap_err(),
        DiscoveryError::UnsupportedProfile
    );
    assert!(server.requests.lock().unwrap().is_empty());
    let wrong = ManagedLocalContext {
        installation_id: Uuid::from_u128(2),
        ..context(&server)
    };
    assert_eq!(
        discover_with_context(&server.base, DiscoveryOptions::default(), Some(&wrong))
            .await
            .unwrap_err(),
        DiscoveryError::IdentityMismatch
    );
}

#[tokio::test]
async fn per_request_and_total_budgets_bound_stalled_discovery() {
    for (total, request) in [(1000, 80), (80, 1000)] {
        let server = server(false, "", Fault::Slow, false, false).await;
        let started = std::time::Instant::now();
        let error = discover_with_budget(
            &server.base,
            DiscoveryOptions::default(),
            Some(&context(&server)),
            Duration::from_millis(total),
            Duration::from_millis(request),
        )
        .await
        .unwrap_err();
        assert_eq!(error, DiscoveryError::Timeout);
        assert!(started.elapsed() < Duration::from_secs(2));
        assert_eq!(server.requests.lock().unwrap().len(), 1);
    }
}

#[tokio::test]
async fn cancellation_drops_the_original_discovery_without_retry() {
    let server = server(false, "", Fault::Slow, false, false).await;
    let base = server.base.clone();
    let managed = context(&server);
    for alias in [
        base.replace("127.0.0.1", "127.1"),
        base.replace("127.0.0.1", "2130706433"),
    ] {
        assert!(UrlPolicy::new(Some(&managed)).api_url(&alias).is_err());
    }
    let task = tokio::spawn(async move {
        discover_with_context(&base, DiscoveryOptions::default(), Some(&managed)).await
    });
    tokio::time::timeout(Duration::from_secs(2), async {
        while server.requests.lock().unwrap().is_empty() {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    task.abort();
    assert!(
        tokio::time::timeout(Duration::from_secs(1), task)
            .await
            .unwrap()
            .unwrap_err()
            .is_cancelled()
    );
    assert_eq!(server.requests.lock().unwrap().len(), 1);
}

#[tokio::test]
async fn separately_hosted_issuer_uses_its_own_verified_origin() {
    for tls in [false, true] {
        let issuer = server(tls, "", Fault::None, false, false).await;
        let api = server_with_issuer(tls, "", Fault::None, false, false, |_| {
            format!("{}/issuer/", issuer.base)
        })
        .await;
        let options = DiscoveryOptions {
            certificate_authorities: vec![api.ca.clone(), issuer.ca.clone()],
            proxy: None,
        };
        let managed = ManagedLocalContext {
            installation_id: Uuid::from_u128(1),
            api_origin: Url::parse(&api.base).unwrap().origin(),
            issuer_origin: Url::parse(&issuer.base).unwrap().origin(),
        };
        let result = discover_with_context(&api.base, options, (!tls).then_some(&managed))
            .await
            .unwrap();
        assert_eq!(
            result.provider.issuer().as_str(),
            format!("{}/issuer/", issuer.base)
        );
        assert_eq!(api.requests.lock().unwrap().len(), 1);
        assert_eq!(issuer.requests.lock().unwrap().len(), 2);
    }
}

struct TunnelProxy {
    url: String,
    requests: Arc<Mutex<Vec<String>>>,
    task: JoinHandle<()>,
}

impl Drop for TunnelProxy {
    fn drop(&mut self) {
        self.task.abort();
    }
}

async fn tunnel_proxy(destination: &str) -> TunnelProxy {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("http://{}", listener.local_addr().unwrap());
    let requests = Arc::new(Mutex::new(Vec::new()));
    let records = requests.clone();
    let destination = destination.strip_prefix("https://").unwrap().to_owned();
    let task = tokio::spawn(async move {
        let mut children = JoinSet::new();
        loop {
            tokio::select! {
                connection = listener.accept() => {
                    let (mut client, _) = connection.unwrap();
                    let (records, destination) = (records.clone(), destination.clone());
                    children.spawn(async move {
                        let mut headers = Vec::new();
                        while !headers.ends_with(b"\r\n\r\n") {
                            let mut byte = [0];
                            if client.read_exact(&mut byte).await.is_err() { return; }
                            headers.push(byte[0]);
                            assert!(headers.len() < 16_384);
                        }
                        let request = String::from_utf8(headers).unwrap();
                        assert!(request.starts_with(&format!("CONNECT {destination} ")));
                        records.lock().unwrap().push(request);
                        let mut upstream = tokio::net::TcpStream::connect(&destination).await.unwrap();
                        client.write_all(b"HTTP/1.1 200 Connection Established\r\n\r\n").await.unwrap();
                        let _ = tokio::io::copy_bidirectional(&mut client, &mut upstream).await;
                    });
                },
                result = children.join_next(), if !children.is_empty() => { result.unwrap().unwrap(); }
            }
        }
    });
    TunnelProxy {
        url,
        requests,
        task,
    }
}

#[tokio::test]
async fn verified_https_discovery_supports_an_explicit_connect_proxy() {
    let server = server(true, "", Fault::None, false, false).await;
    let proxy = tunnel_proxy(&server.base).await;
    let result = discover(
        &server.base,
        DiscoveryOptions {
            certificate_authorities: vec![server.ca.clone()],
            proxy: Some(reqwest::Proxy::all(&proxy.url).unwrap()),
        },
    )
    .await
    .unwrap();
    assert_eq!(result.resource, server.base);
    assert_eq!(server.requests.lock().unwrap().len(), 3);
    assert!(!proxy.requests.lock().unwrap().is_empty());
}
