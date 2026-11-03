//! Synthetic TLS/process evidence exercises the production flow, not native Ory or UI.
#![allow(clippy::unwrap_used)]

use std::{
    collections::BTreeMap,
    convert::Infallible,
    sync::{Arc, Mutex},
    time::{Duration, SystemTime},
};

use bytes::Bytes;
use http_body_util::{BodyExt, Full, Limited};
use hyper::{Request, Response, body::Incoming, service::service_fn};
use hyper_util::rt::TokioIo;
use inframeld_cli::{
    auth::{
        flow::{AuthorizationReady, BrowserLaunchError, BrowserLauncher, HostContext, repair},
        maintenance_handoff::{CleanupStatus, ExecutionSpec, MaintenanceEffect},
    },
    discovery::DiscoveryOptions,
};
use openidconnect::{
    AccessToken, Audience, ClientId, EmptyAdditionalClaims, IssuerUrl, JsonWebKeyId, Nonce,
    PkceCodeChallenge, PkceCodeVerifier, PrivateSigningKey, StandardClaims, SubjectIdentifier,
    core::{CoreEdDsaPrivateSigningKey, CoreIdToken, CoreIdTokenClaims, CoreJwsSigningAlgorithm},
};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::{TcpListener, TcpStream},
    sync::oneshot,
    task::JoinHandle,
    time::Instant,
};
use tokio_rustls::TlsAcceptor;
use uuid::Uuid;

#[derive(Clone, Copy)]
enum ProviderBehavior {
    Valid,
    Denied,
    WrongNonce,
    WrongIssuer,
    WrongAudience,
    WrongAzp,
    MissingAzpForMultipleAudiences,
    WrongAccessHash,
    WrongSubject,
    Expired,
    WrongSignature,
    RefreshRevocationRejected,
    SessionDenied,
    SessionRedirect,
    SessionOversize,
    SessionUnavailable,
    TokenOversize,
    TokenRedirect,
}

struct State {
    behavior: ProviderBehavior,
    revoked: Vec<String>,
    api: String,
    issuer: String,
    signing_key: CoreEdDsaPrivateSigningKey,
    nonce: String,
    challenge: String,
    redirect: String,
    calls: BTreeMap<String, usize>,
}

// Keep this fixture's closed protocol routes and rejection scenarios together.
#[allow(clippy::too_many_lines)]
async fn response(request: Request<Incoming>, state: &Mutex<State>) -> Response<Full<Bytes>> {
    let path = request.uri().path().to_owned();
    let query = request.uri().query().unwrap_or("").to_owned();
    let bearer = request.headers().get(http::header::AUTHORIZATION).cloned();
    let body = Limited::new(request.into_body(), 65_536)
        .collect()
        .await
        .unwrap()
        .to_bytes();
    let mut state = state.lock().unwrap();
    *state.calls.entry(path.clone()).or_default() += 1;
    let mut status = 200;
    let mut location = None;
    let payload = match path.as_str() {
        "/.well-known/oauth-protected-resource/api" => {
            serde_json::json!({"resource":state.api,"authorization_servers":[state.issuer],"scopes_supported":["inframeld:api"],"bearer_methods_supported":["header"],"inframeld":{"installation_id":Uuid::from_u128(1),"client_id":"inframeld-cli","schema_version":1}})
        }
        "/issuer/.well-known/openid-configuration" => {
            serde_json::json!({"issuer":state.issuer,"authorization_endpoint":format!("{}authorize",state.issuer),"token_endpoint":format!("{}token",state.issuer),"revocation_endpoint":format!("{}revoke",state.issuer),"jwks_uri":format!("{}keys",state.issuer),"grant_types_supported":["authorization_code","refresh_token"],"response_types_supported":["code"],"token_endpoint_auth_methods_supported":["none"],"subject_types_supported":["public"],"id_token_signing_alg_values_supported":["EdDSA"],"code_challenge_methods_supported":["S256"]})
        }
        "/issuer/keys" => serde_json::json!({"keys":[state.signing_key.as_verification_key()]}),
        "/issuer/authorize" => {
            let parameters: BTreeMap<_, _> = url::form_urlencoded::parse(query.as_bytes())
                .into_owned()
                .collect();
            assert!(parameters["client_id"] == "inframeld-cli");
            assert!(parameters["response_type"] == "code");
            assert!(parameters["code_challenge_method"] == "S256");
            assert!(parameters["audience"] == state.api);
            assert!(
                parameters["scope"]
                    .split(' ')
                    .all(|scope| matches!(scope, "openid" | "inframeld:api"))
            );
            state.nonce.clone_from(&parameters["nonce"]);
            state.challenge.clone_from(&parameters["code_challenge"]);
            state.redirect.clone_from(&parameters["redirect_uri"]);
            let mut callback = url::Url::parse(&state.redirect).unwrap();
            callback
                .query_pairs_mut()
                .append_pair(
                    if matches!(state.behavior, ProviderBehavior::Denied) {
                        "error"
                    } else {
                        "code"
                    },
                    if matches!(state.behavior, ProviderBehavior::Denied) {
                        "access_denied"
                    } else {
                        "synthetic-code"
                    },
                )
                .append_pair("state", &parameters["state"]);
            location = Some(callback.to_string());
            status = 302;
            serde_json::json!({})
        }
        "/issuer/token" => {
            assert!(bearer.is_none());
            let parameters: BTreeMap<_, _> =
                url::form_urlencoded::parse(&body).into_owned().collect();
            assert!(parameters["client_id"] == "inframeld-cli");
            assert!(parameters["code"] == "synthetic-code");
            assert!(parameters["redirect_uri"] == state.redirect);
            assert!(
                PkceCodeChallenge::from_code_verifier_sha256(&PkceCodeVerifier::new(
                    parameters["code_verifier"].clone()
                ))
                .as_str()
                    == state.challenge
            );
            let behavior = state.behavior;
            let issuer = if matches!(behavior, ProviderBehavior::WrongIssuer) {
                "https://other.test/".into()
            } else {
                state.issuer.clone()
            };
            let audiences = match behavior {
                ProviderBehavior::WrongAudience => vec![Audience::new("other-client".into())],
                ProviderBehavior::MissingAzpForMultipleAudiences => vec![
                    Audience::new("inframeld-cli".into()),
                    Audience::new("other-client".into()),
                ],
                _ => vec![Audience::new("inframeld-cli".into())],
            };
            let expiry = if matches!(behavior, ProviderBehavior::Expired) {
                SystemTime::now() - Duration::from_mins(5)
            } else {
                SystemTime::now() + Duration::from_mins(1)
            };
            let subject = if matches!(behavior, ProviderBehavior::WrongSubject) {
                Uuid::from_u128(99)
            } else {
                Uuid::from_u128(2)
            };
            let nonce = if matches!(behavior, ProviderBehavior::WrongNonce) {
                "other-nonce".into()
            } else {
                state.nonce.clone()
            };
            let claims = CoreIdTokenClaims::new(
                IssuerUrl::new(issuer).unwrap(),
                audiences,
                expiry.into(),
                SystemTime::now().into(),
                StandardClaims::new(SubjectIdentifier::new(subject.to_string())),
                EmptyAdditionalClaims {},
            )
            .set_nonce(Some(Nonce::new(nonce)))
            .set_authorized_party(
                matches!(behavior, ProviderBehavior::WrongAzp)
                    .then(|| ClientId::new("other-client".into())),
            );
            let other_key = rcgen::KeyPair::generate_for(&rcgen::PKCS_ED25519).unwrap();
            let other_key = CoreEdDsaPrivateSigningKey::from_ed25519_pem(
                &other_key.serialize_pem(),
                Some(JsonWebKeyId::new("synthetic-key".into())),
            )
            .unwrap();
            let key = if matches!(behavior, ProviderBehavior::WrongSignature) {
                &other_key
            } else {
                &state.signing_key
            };
            let hashed_access = if matches!(behavior, ProviderBehavior::WrongAccessHash) {
                "other-access-token"
            } else {
                "synthetic-access-token"
            };
            let token = CoreIdToken::new(
                claims,
                key,
                CoreJwsSigningAlgorithm::EdDsa,
                Some(&AccessToken::new(hashed_access.into())),
                None,
            )
            .unwrap();
            let mut payload = serde_json::json!({"access_token":"synthetic-access-token","token_type":"Bearer","expires_in":60,"scope":"openid inframeld:api","id_token":token});
            match behavior {
                ProviderBehavior::RefreshRevocationRejected => {
                    payload["refresh_token"] = serde_json::json!("synthetic-refresh-token");
                }
                ProviderBehavior::TokenOversize => {
                    payload["padding"] = serde_json::json!("x".repeat(65_536));
                }
                ProviderBehavior::TokenRedirect => {
                    status = 302;
                    location = Some(format!("{}/unexpected", state.issuer));
                }
                _ => {}
            }
            payload
        }
        "/api/v1/session" => {
            assert!(
                bearer
                    .as_ref()
                    .is_some_and(|value| value == "Bearer synthetic-access-token")
            );
            match state.behavior {
                ProviderBehavior::SessionDenied => {
                    status = 403;
                    serde_json::json!({"detail":"synthetic protected denial"})
                }
                ProviderBehavior::SessionRedirect => {
                    status = 302;
                    location = Some(format!("{}/unexpected", state.api));
                    serde_json::json!({})
                }
                ProviderBehavior::SessionOversize => {
                    serde_json::json!({"principalId":Uuid::from_u128(10),"padding":"x".repeat(65_536)})
                }
                ProviderBehavior::SessionUnavailable => {
                    status = 503;
                    serde_json::json!({})
                }
                _ => serde_json::json!({"principalId":Uuid::from_u128(10)}),
            }
        }
        "/issuer/revoke" => {
            let parameters: BTreeMap<_, _> =
                url::form_urlencoded::parse(&body).into_owned().collect();
            let token = parameters["token"].clone();
            assert!(matches!(
                token.as_str(),
                "synthetic-access-token" | "synthetic-refresh-token"
            ));
            if token == "synthetic-refresh-token" {
                status = 500;
            }
            state.revoked.push(token);
            serde_json::json!({})
        }
        _ => {
            status = 404;
            serde_json::json!({})
        }
    };
    let mut response = Response::new(Full::new(Bytes::from(
        serde_json::to_vec(&payload).unwrap(),
    )));
    *response.status_mut() = http::StatusCode::from_u16(status).unwrap();
    response.headers_mut().insert(
        http::header::CONTENT_TYPE,
        http::HeaderValue::from_static("application/json"),
    );
    if let Some(location) = location {
        response.headers_mut().insert(
            http::header::LOCATION,
            http::HeaderValue::from_str(&location).unwrap(),
        );
    }
    response
}

struct Provider {
    base: String,
    ca: reqwest::Certificate,
    state: Arc<Mutex<State>>,
    stop: Option<oneshot::Sender<()>>,
    task: Option<JoinHandle<()>>,
}
impl Provider {
    async fn start() -> Self {
        let _ = rustls::crypto::ring::default_provider().install_default();
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let base = format!("https://{}", listener.local_addr().unwrap());
        let key = rcgen::KeyPair::generate().unwrap();
        let certificate = rcgen::CertificateParams::new(vec!["127.0.0.1".into()])
            .unwrap()
            .self_signed(&key)
            .unwrap();
        let ca = reqwest::Certificate::from_der(certificate.der()).unwrap();
        let config = rustls::ServerConfig::builder_with_provider(Arc::new(
            rustls::crypto::ring::default_provider(),
        ))
        .with_safe_default_protocol_versions()
        .unwrap()
        .with_no_client_auth()
        .with_single_cert(
            vec![certificate.der().clone()],
            rustls::pki_types::PrivatePkcs8KeyDer::from(key.serialize_der()).into(),
        )
        .unwrap();
        let acceptor = TlsAcceptor::from(Arc::new(config));
        let signing = rcgen::KeyPair::generate_for(&rcgen::PKCS_ED25519).unwrap();
        let state = Arc::new(Mutex::new(State {
            behavior: ProviderBehavior::Valid,
            revoked: Vec::new(),
            api: format!("{base}/api"),
            issuer: format!("{base}/issuer/"),
            signing_key: CoreEdDsaPrivateSigningKey::from_ed25519_pem(
                &signing.serialize_pem(),
                Some(JsonWebKeyId::new("synthetic-key".into())),
            )
            .unwrap(),
            nonce: String::new(),
            challenge: String::new(),
            redirect: String::new(),
            calls: BTreeMap::new(),
        }));
        let (stop, mut stopping) = oneshot::channel();
        let serving = state.clone();
        let task = tokio::spawn(async move {
            loop {
                let socket = tokio::select! {_=&mut stopping=>break,connection=listener.accept()=>connection.unwrap().0};
                let acceptor = acceptor.clone();
                let serving = serving.clone();
                let connection = async {
                    let socket = acceptor.accept(socket).await.unwrap();
                    let service = service_fn(|request| async {
                        Ok::<_, Infallible>(response(request, &serving).await)
                    });
                    let _ = hyper::server::conn::http1::Builder::new()
                        .keep_alive(false)
                        .serve_connection(TokioIo::new(socket), service)
                        .await;
                };
                tokio::select! {_=&mut stopping=>break,()=connection=>{}}
            }
        });
        Self {
            base,
            ca,
            state,
            stop: Some(stop),
            task: Some(task),
        }
    }
    fn host(&self) -> HostContext {
        HostContext::new(
            format!("{}/api", self.base),
            format!("{}/issuer/", self.base),
            "inframeld-cli".into(),
            Uuid::from_u128(1),
            Uuid::from_u128(2),
            DiscoveryOptions {
                certificate_authorities: vec![self.ca.clone()],
                proxy: None,
            },
        )
    }
    async fn finish(mut self) {
        let _ = self.stop.take().unwrap().send(());
        tokio::time::timeout(Duration::from_secs(1), self.task.take().unwrap())
            .await
            .unwrap()
            .unwrap();
    }
}
impl Drop for Provider {
    fn drop(&mut self) {
        if let Some(task) = &self.task {
            task.abort();
        }
    }
}

struct Browser {
    client: reqwest::Client,
    callback: Option<TcpStream>,
    opened: bool,
    advance_to_final_window: bool,
}
impl BrowserLauncher for Browser {
    async fn open(
        &mut self,
        ready: &AuthorizationReady,
        deadline: Instant,
        _cancellation: std::pin::Pin<&mut (dyn std::future::Future<Output = ()> + Send)>,
    ) -> Result<(), BrowserLaunchError> {
        self.opened = true;
        let response = self
            .client
            .get(ready.authorization_url.clone())
            .send()
            .await
            .map_err(|_| BrowserLaunchError::failed())?;
        if response.status() != 302 {
            return Err(BrowserLaunchError::failed());
        }
        let location = response
            .headers()
            .get(http::header::LOCATION)
            .and_then(|value| value.to_str().ok())
            .ok_or_else(BrowserLaunchError::failed)?;
        let callback = url::Url::parse(location).map_err(|_| BrowserLaunchError::failed())?;
        let host = format!(
            "127.0.0.1:{}",
            callback.port().ok_or_else(BrowserLaunchError::failed)?
        );
        let mut socket = TcpStream::connect(&host)
            .await
            .map_err(|_| BrowserLaunchError::failed())?;
        socket
            .write_all(
                format!(
                    "GET {}?{} HTTP/1.1\r\nHost: {host}\r\n\r\n",
                    callback.path(),
                    callback.query().ok_or_else(BrowserLaunchError::failed)?
                )
                .as_bytes(),
            )
            .await
            .map_err(|_| BrowserLaunchError::failed())?;
        self.callback = Some(socket);
        if self.advance_to_final_window {
            // No provider request is in flight. Advance only this controlled
            // callback boundary, then return to real I/O for exchange/session.
            tokio::time::pause();
            tokio::time::advance(
                deadline
                    .saturating_duration_since(Instant::now())
                    .checked_sub(Duration::from_millis(200))
                    .unwrap(),
            )
            .await;
            tokio::time::resume();
        }
        Ok(())
    }
}

fn request() -> Vec<u8> {
    br#"{"schemaVersion":1,"mode":"repair-stranded-authority","expectedInstallationId":"00000000-0000-0000-0000-000000000001","operationId":"original-operation","operatorLabel":"Alice","reason":"reviewed repair","expectedAccessRevision":4,"expectedIdentityId":"00000000-0000-0000-0000-000000000002","responsibility":{"kind":"action-grantor","target":{"kind":"project","projectId":"00000000-0000-0000-0000-000000000003"},"actionId":"edit-project-metadata"}}"#.to_vec()
}

fn execution() -> (tempfile::TempDir, ExecutionSpec) {
    let directory = tempfile::tempdir().unwrap();
    let script = directory.path().join("maintenance.py");
    std::fs::write(&script,r"import json, sys
request=json.load(sys.stdin)
assert request['identityProof']=={'kind':'hydra-access-token','accessToken':'synthetic-access-token'}
print(json.dumps({'schemaVersion':1,'mode':request['mode'],'operationId':request['operationId'],'installationId':request['expectedInstallationId'],'principalId':'00000000-0000-0000-0000-00000000000a','accessRevision':request['expectedAccessRevision']+1,'outcome':'repaired','responsibility':request['responsibility']}))
").unwrap();
    let python = std::process::Command::new("python3")
        .args(["-c", "import sys; print(sys.executable)"])
        .output()
        .unwrap();
    assert!(python.status.success());
    let program = String::from_utf8(python.stdout).unwrap();
    let spec = ExecutionSpec::parse(
        &serde_json::to_vec(
            &serde_json::json!({"program":program.trim(),"args":[script],"environment":{}}),
        )
        .unwrap(),
    )
    .unwrap();
    (directory, spec)
}

#[tokio::test]
async fn complete_shared_flow_uses_pkce_verified_identity_generated_session_and_one_protected_submission()
 {
    let provider = Provider::start().await;
    let (_directory, execution) = execution();
    let mut browser = Browser {
        client: reqwest::Client::builder()
            .no_proxy()
            .add_root_certificate(provider.ca.clone())
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .timeout(Duration::from_secs(1))
            .build()
            .unwrap(),
        callback: None,
        opened: false,
        advance_to_final_window: false,
    };
    let outcome = repair(
        &provider.host(),
        &request(),
        &execution,
        &mut browser,
        std::future::pending(),
    )
    .await;
    assert!(outcome.is_ok());
    let outcome = outcome.unwrap();
    assert!(matches!(
        outcome.maintenance.effect,
        MaintenanceEffect::Committed { .. }
    ));
    assert_eq!(outcome.credential_cleanup, CleanupStatus::Confirmed);
    assert_eq!(
        outcome.maintenance.process_cleanup,
        CleanupStatus::Confirmed
    );
    assert!(browser.opened);
    if let Some(mut socket) = browser.callback.take() {
        let mut bytes = Vec::new();
        let _ = socket.read_to_end(&mut bytes).await;
    }
    {
        let state = provider.state.lock().unwrap();
        assert_eq!(state.calls.get("/issuer/token"), Some(&1));
        assert_eq!(state.calls.get("/api/v1/session"), Some(&1));
        assert_eq!(state.calls.get("/issuer/revoke"), Some(&1));
    }
    provider.finish().await;
}

#[tokio::test]
async fn private_browser_bridge_sends_one_bounded_event_and_removes_only_its_socket() {
    use inframeld_cli::auth::maintenance_handoff::NativeBrowserBridge;
    use std::os::unix::fs::PermissionsExt;
    let directory = tempfile::tempdir().unwrap();
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
    let path = directory.path().join("browser.sock");
    let mut bridge = NativeBrowserBridge::new(path.clone());
    let ready = AuthorizationReady {
        authorization_url: url::Url::parse("https://identity.test/authorize?state=synthetic-state")
            .unwrap(),
        issuer: "https://identity.test/".into(),
        callback_uri: "http://127.0.0.1:49152/oauth/callback/expected-digest".into(),
    };
    let mut cancellation = std::pin::pin!(std::future::pending::<()>());
    let peer = async {
        let deadline = Instant::now() + Duration::from_millis(150);
        let mut socket = loop {
            match tokio::net::UnixStream::connect(&path).await {
                Ok(socket) => break socket,
                Err(_) if Instant::now() < deadline => {
                    tokio::time::sleep(Duration::from_millis(5)).await;
                }
                Err(_) => return None,
            }
        };
        let mut event = Vec::new();
        tokio::time::timeout(Duration::from_secs(1), socket.read_to_end(&mut event))
            .await
            .unwrap()
            .unwrap();
        Some(event)
    };
    let (result, event) = tokio::join!(
        bridge.open(
            &ready,
            Instant::now() + Duration::from_secs(1),
            cancellation.as_mut()
        ),
        peer
    );
    assert!(result.is_ok(), "{result:?}");
    let event: serde_json::Value = serde_json::from_slice(&event.unwrap()).unwrap();
    assert_eq!(event["schemaVersion"], 1);
    assert_eq!(event["type"], "authorization-ready");
    assert_eq!(event["authorizationUrl"], ready.authorization_url.as_str());
    assert_eq!(event.as_object().unwrap().len(), 5);
    assert!(!path.exists());
    assert_eq!(std::fs::read_dir(directory.path()).unwrap().count(), 0);
}

fn browser(provider: &Provider) -> Browser {
    Browser {
        client: reqwest::Client::builder()
            .no_proxy()
            .add_root_certificate(provider.ca.clone())
            .redirect(reqwest::redirect::Policy::none())
            .retry(reqwest::retry::never())
            .timeout(Duration::from_secs(1))
            .build()
            .unwrap(),
        callback: None,
        opened: false,
        advance_to_final_window: false,
    }
}

#[tokio::test]
async fn denied_authorization_admits_no_exchange_session_maintenance_or_revocation() {
    use inframeld_cli::auth::flow::FailureKind;
    let provider = Provider::start().await;
    provider.state.lock().unwrap().behavior = ProviderBehavior::Denied;
    let (directory, execution) = execution();
    let marker = directory.path().join("maintenance-started");
    let script = directory.path().join("maintenance.py");
    let original = std::fs::read_to_string(&script).unwrap();
    std::fs::write(
        &script,
        format!(
            "from pathlib import Path\nPath({}).write_text('started')\n{original}",
            serde_json::to_string(marker.to_str().unwrap()).unwrap()
        ),
    )
    .unwrap();
    let mut browser = browser(&provider);
    let result = repair(
        &provider.host(),
        &request(),
        &execution,
        &mut browser,
        std::future::pending(),
    )
    .await;
    let calls = provider.state.lock().unwrap().calls.clone();
    drop(browser);
    provider.finish().await;
    assert_eq!(result.unwrap_err().kind, FailureKind::Denied);
    assert!(!marker.exists());
    for endpoint in ["/issuer/token", "/api/v1/session", "/issuer/revoke"] {
        assert!(!calls.contains_key(endpoint));
    }
}

#[tokio::test]
async fn rejected_identity_and_session_never_reach_maintenance_or_follow_redirects_or_retry() {
    use inframeld_cli::auth::flow::FailureKind;
    for behavior in [
        ProviderBehavior::WrongNonce,
        ProviderBehavior::WrongIssuer,
        ProviderBehavior::WrongAudience,
        ProviderBehavior::WrongAzp,
        ProviderBehavior::MissingAzpForMultipleAudiences,
        ProviderBehavior::WrongAccessHash,
        ProviderBehavior::WrongSubject,
        ProviderBehavior::Expired,
        ProviderBehavior::WrongSignature,
        ProviderBehavior::SessionDenied,
        ProviderBehavior::SessionRedirect,
        ProviderBehavior::SessionOversize,
        ProviderBehavior::SessionUnavailable,
        ProviderBehavior::TokenOversize,
        ProviderBehavior::TokenRedirect,
    ] {
        let provider = Provider::start().await;
        provider.state.lock().unwrap().behavior = behavior;
        let (directory, execution) = execution();
        let marker = directory.path().join("maintenance-started");
        let script = directory.path().join("maintenance.py");
        let original = std::fs::read_to_string(&script).unwrap();
        std::fs::write(
            &script,
            format!(
                "open({},'w').write('started')\n{original}",
                serde_json::to_string(marker.to_str().unwrap()).unwrap()
            ),
        )
        .unwrap();
        let error = repair(
            &provider.host(),
            &request(),
            &execution,
            &mut browser(&provider),
            std::future::pending(),
        )
        .await
        .unwrap_err();
        let session = matches!(
            behavior,
            ProviderBehavior::SessionDenied
                | ProviderBehavior::SessionRedirect
                | ProviderBehavior::SessionOversize
                | ProviderBehavior::SessionUnavailable
        );
        let exchange = matches!(
            behavior,
            ProviderBehavior::TokenOversize | ProviderBehavior::TokenRedirect
        );
        assert_eq!(
            error.kind,
            if session {
                FailureKind::Session
            } else if exchange {
                FailureKind::Exchange
            } else {
                FailureKind::Identity
            }
        );
        assert_eq!(
            error.credential_cleanup,
            if exchange {
                CleanupStatus::Unconfirmed
            } else {
                CleanupStatus::Confirmed
            }
        );
        assert!(!marker.exists());
        assert!(!format!("{error:?}").contains("synthetic-access-token"));
        {
            let state = provider.state.lock().unwrap();
            assert_eq!(state.calls.get("/issuer/token"), Some(&1));
            assert_eq!(
                state.calls.get("/api/v1/session"),
                if session { Some(&1) } else { None }
            );
            assert!(
                state
                    .calls
                    .keys()
                    .all(|path| !path.ends_with("/unexpected"))
            );
        }
        provider.finish().await;
    }
}

#[tokio::test]
async fn unexpected_refresh_rejects_repair_and_attempts_both_new_credential_revocations() {
    use inframeld_cli::auth::flow::FailureKind;
    let provider = Provider::start().await;
    provider.state.lock().unwrap().behavior = ProviderBehavior::RefreshRevocationRejected;
    let (_directory, execution) = execution();
    let error = repair(
        &provider.host(),
        &request(),
        &execution,
        &mut browser(&provider),
        std::future::pending(),
    )
    .await
    .unwrap_err();
    assert_eq!(error.kind, FailureKind::UnexpectedRefresh);
    assert_eq!(error.credential_cleanup, CleanupStatus::Unconfirmed);
    {
        let state = provider.state.lock().unwrap();
        assert_eq!(
            state.revoked,
            ["synthetic-refresh-token", "synthetic-access-token"]
        );
        assert!(!state.calls.contains_key("/api/v1/session"));
    }
    provider.finish().await;
}

#[tokio::test]
async fn original_interaction_deadline_also_bounds_the_complete_session_and_maintenance_flow() {
    use inframeld_cli::auth::maintenance_handoff::HandoffFailure;
    let provider = Provider::start().await;
    let (directory, execution) = execution();
    let script = directory.path().join("maintenance.py");
    let original = std::fs::read_to_string(&script).unwrap();
    std::fs::write(
        &script,
        format!("{original}\nimport time\nsys.stdout.flush()\ntime.sleep(30)\n"),
    )
    .unwrap();
    let mut browser = browser(&provider);
    browser.advance_to_final_window = true;
    let started = Instant::now();
    let outcome = repair(
        &provider.host(),
        &request(),
        &execution,
        &mut browser,
        std::future::pending(),
    )
    .await
    .unwrap();
    assert!(matches!(
        outcome.maintenance.effect,
        MaintenanceEffect::Committed { .. }
    ));
    assert_eq!(outcome.maintenance.failure, Some(HandoffFailure::TimedOut));
    assert_eq!(
        outcome.maintenance.process_cleanup,
        CleanupStatus::Confirmed
    );
    assert_eq!(outcome.credential_cleanup, CleanupStatus::Confirmed);
    assert!(Instant::now() - started >= Duration::from_mins(10));
    assert!(Instant::now() - started < Duration::from_mins(10) + Duration::from_secs(1));
    {
        let state = provider.state.lock().unwrap();
        assert_eq!(state.calls.get("/issuer/token"), Some(&1));
        assert_eq!(state.calls.get("/api/v1/session"), Some(&1));
        assert_eq!(state.calls.get("/issuer/revoke"), Some(&1));
    }
    provider.finish().await;
}

#[tokio::test]
async fn expired_browser_intent_creates_no_socket_or_cleanup_obligation() {
    use inframeld_cli::auth::{flow::BrowserFailureKind, maintenance_handoff::NativeBrowserBridge};
    use std::os::unix::fs::PermissionsExt;
    let directory = tempfile::tempdir().unwrap();
    std::fs::set_permissions(directory.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
    let path = directory.path().join("browser.sock");
    let mut bridge = NativeBrowserBridge::new(path.clone());
    let ready = AuthorizationReady {
        authorization_url: url::Url::parse("https://identity.test/authorize?state=synthetic")
            .unwrap(),
        issuer: "https://identity.test/".into(),
        callback_uri: "http://127.0.0.1:49152/oauth/callback/digest".into(),
    };
    let mut cancellation = std::pin::pin!(std::future::pending::<()>());
    let error = bridge
        .open(
            &ready,
            Instant::now() - Duration::from_millis(1),
            cancellation.as_mut(),
        )
        .await
        .unwrap_err();
    assert_eq!(error.kind, BrowserFailureKind::TimedOut);
    assert_eq!(error.resource_cleanup, CleanupStatus::NotNeeded);
    assert!(!path.exists());
}

#[tokio::test]
async fn invalid_or_bootstrap_or_misbound_intent_is_rejected_before_discovery_or_browser() {
    use inframeld_cli::auth::flow::FailureKind;
    let provider = Provider::start().await;
    let (_directory, execution) = execution();
    for (field, value, expected) in [
        (
            "mode",
            serde_json::json!("bootstrap-first-administrator"),
            FailureKind::InvalidRequest,
        ),
        (
            "identityProof",
            serde_json::json!({"kind":"hydra-access-token","accessToken":"never-accepted"}),
            FailureKind::InvalidRequest,
        ),
        (
            "reason",
            serde_json::json!("\u{001c}\u{001f}"),
            FailureKind::InvalidRequest,
        ),
        (
            "expectedIdentityId",
            serde_json::json!(Uuid::from_u128(99)),
            FailureKind::Binding,
        ),
    ] {
        let mut request: serde_json::Value = serde_json::from_slice(&request()).unwrap();
        request[field] = value;
        let mut browser = browser(&provider);
        let error = repair(
            &provider.host(),
            &serde_json::to_vec(&request).unwrap(),
            &execution,
            &mut browser,
            std::future::pending(),
        )
        .await
        .unwrap_err();
        assert_eq!(error.kind, expected);
        assert_eq!(error.credential_cleanup, CleanupStatus::NotNeeded);
        assert!(!browser.opened);
        assert!(provider.state.lock().unwrap().calls.is_empty());
    }
    provider.finish().await;
}
