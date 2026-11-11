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
        flow::{
            AuthorizationReady, BrowserLaunchError, BrowserLauncher, HostContext, bootstrap, repair,
        },
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
    AccessRevocationRejected,
    AccessRevocationRedirect,
    AccessRevocationOversize,
    AccessRevocationInvalid,
    AccessRevocationStalled,
    SlowRefreshRevocationRejected,
    SessionDenied,
    SessionRedirect,
    SessionOversize,
    SessionUnavailable,
    TokenOversize,
    TokenRedirect,
    DiscoveryStalled,
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
    routes: Vec<String>,
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
    let delay = {
        let mut state = state.lock().unwrap();
        *state.calls.entry(path.clone()).or_default() += 1;
        state.routes.push(path.clone());
        if path == "/.well-known/oauth-protected-resource/missing"
            && matches!(state.behavior, ProviderBehavior::DiscoveryStalled)
        {
            Some(Duration::from_secs(6))
        } else if path == "/issuer/revoke" {
            match state.behavior {
                ProviderBehavior::AccessRevocationStalled => Some(Duration::from_secs(6)),
                ProviderBehavior::SlowRefreshRevocationRejected => Some(Duration::from_secs(3)),
                _ => None,
            }
        } else {
            None
        }
    };
    if let Some(delay) = delay {
        tokio::time::sleep(delay).await;
    }
    let mut state = state.lock().unwrap();
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
                ProviderBehavior::RefreshRevocationRejected
                | ProviderBehavior::SlowRefreshRevocationRejected => {
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
            match state.behavior {
                ProviderBehavior::AccessRevocationRejected => {
                    status = 400;
                    serde_json::json!({"error":"invalid_request","error_description":"protected-provider-sentinel"})
                }
                ProviderBehavior::AccessRevocationRedirect => {
                    status = 302;
                    location = Some(format!("{}unexpected", state.issuer));
                    serde_json::json!({})
                }
                ProviderBehavior::AccessRevocationOversize => {
                    serde_json::json!({"padding":"protected-provider-sentinel".repeat(4000)})
                }
                ProviderBehavior::AccessRevocationInvalid => {
                    status = 400;
                    serde_json::json!({})
                }
                _ => serde_json::json!({}),
            }
        }
        _ => {
            status = 404;
            serde_json::json!({})
        }
    };
    let bytes = if path == "/issuer/revoke"
        && matches!(state.behavior, ProviderBehavior::AccessRevocationInvalid)
    {
        b"protected-provider-sentinel".to_vec()
    } else {
        serde_json::to_vec(&payload).unwrap()
    };
    let mut response = Response::new(Full::new(Bytes::from(bytes)));
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
    ca_pem: String,
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
            routes: Vec::new(),
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
            ca_pem: certificate.pem(),
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
                    .checked_sub(Duration::from_secs(3))
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

fn bootstrap_request() -> Vec<u8> {
    let mut value: serde_json::Value = serde_json::from_slice(&request()).unwrap();
    value["mode"] = serde_json::json!("bootstrap-first-administrator");
    value["expectedAccessRevision"] = serde_json::json!(0);
    value.as_object_mut().unwrap().remove("responsibility");
    serde_json::to_vec(&value).unwrap()
}

fn bootstrap_execution() -> (tempfile::TempDir, ExecutionSpec) {
    let (directory, execution) = execution();
    std::fs::write(directory.path().join("maintenance.py"), r"import json, sys
request=json.load(sys.stdin)
assert len(request)==9
assert request['identityProof']=={'kind':'hydra-access-token','accessToken':'synthetic-access-token'}
assert request['mode']=='bootstrap-first-administrator'
assert request['expectedAccessRevision']==0
assert 'responsibility' not in request
print(json.dumps({'schemaVersion':1,'mode':request['mode'],'operationId':request['operationId'],'installationId':request['expectedInstallationId'],'principalId':'00000000-0000-0000-0000-00000000000a','accessRevision':1,'outcome':'bootstrapped'}))
").unwrap();
    (directory, execution)
}

#[tokio::test]
async fn bootstrap_claim_accepts_verified_unadmitted_identity_without_preclaim_session() {
    let provider = Provider::start().await;
    provider.state.lock().unwrap().behavior = ProviderBehavior::SessionDenied;
    let (_directory, execution) = bootstrap_execution();
    let outcome = bootstrap(
        &provider.host(),
        &bootstrap_request(),
        &execution,
        &mut browser(&provider),
        false,
        std::future::pending(),
    )
    .await;
    let calls = provider.state.lock().unwrap().calls.clone();
    provider.finish().await;
    assert_eq!(calls.get("/api/v1/session"), None);
    assert_eq!(calls.get("/issuer/token"), Some(&1));
    assert_eq!(calls.get("/issuer/revoke"), Some(&1));
    assert!(
        outcome.is_ok(),
        "verified unadmitted bootstrap must reach the host claim"
    );
    let outcome = outcome.unwrap();
    assert!(matches!(
        outcome.maintenance.effect,
        MaintenanceEffect::Committed { .. }
    ));
    assert_eq!(
        outcome.maintenance.process_cleanup,
        CleanupStatus::Confirmed
    );
    assert_eq!(outcome.credential_cleanup, CleanupStatus::Confirmed);
}

#[tokio::test]
async fn bootstrap_current_admission_does_not_replace_a_missing_original_receipt() {
    use inframeld_cli::auth::flow::SessionObservation;
    let provider = Provider::start().await;
    let (directory, execution) = bootstrap_execution();
    std::fs::write(directory.path().join("maintenance.py"),
        "import json, sys\nrequest=json.load(sys.stdin)\nassert request['identityProof']['kind']=='hydra-access-token'\n").unwrap();
    let outcome = bootstrap(
        &provider.host(),
        &bootstrap_request(),
        &execution,
        &mut browser(&provider),
        true,
        std::future::pending(),
    )
    .await
    .unwrap();
    let routes = provider.state.lock().unwrap().routes.clone();
    provider.finish().await;
    assert!(matches!(outcome.maintenance.effect,
        MaintenanceEffect::Unknown { ref operation_id } if operation_id == "original-operation"));
    assert!(matches!(outcome.current_session,
        SessionObservation::Admitted { principal_id } if principal_id == Uuid::from_u128(10)));
    let safe = serde_json::to_value(&outcome).unwrap();
    assert_eq!(safe["maintenance"]["effect"]["status"], "unknown");
    assert_eq!(
        safe["currentSession"]["principalId"],
        Uuid::from_u128(10).to_string()
    );
    assert!(!safe.to_string().contains("synthetic-access-token"));
    assert!(!format!("{outcome:?}").contains("synthetic-access-token"));
    assert_eq!(
        outcome.maintenance.process_cleanup,
        CleanupStatus::Confirmed
    );
    assert_eq!(outcome.credential_cleanup, CleanupStatus::Confirmed);
    assert!(
        routes
            .iter()
            .position(|path| path == "/api/v1/session")
            .unwrap()
            < routes
                .iter()
                .position(|path| path == "/issuer/revoke")
                .unwrap()
    );
}

#[tokio::test]
async fn bootstrap_receipt_survives_an_unavailable_postclaim_session() {
    use inframeld_cli::auth::flow::SessionObservation;
    let provider = Provider::start().await;
    provider.state.lock().unwrap().behavior = ProviderBehavior::SessionUnavailable;
    let (_directory, execution) = bootstrap_execution();
    let result = bootstrap(
        &provider.host(),
        &bootstrap_request(),
        &execution,
        &mut browser(&provider),
        true,
        std::future::pending(),
    )
    .await
    .unwrap();
    let routes = provider.state.lock().unwrap().routes.clone();
    provider.finish().await;
    assert!(matches!(
        result.maintenance.effect,
        MaintenanceEffect::Committed { .. }
    ));
    assert_eq!(result.current_session, SessionObservation::Unavailable);
    assert_eq!(result.credential_cleanup, CleanupStatus::Confirmed);
    assert_eq!(
        routes
            .iter()
            .filter(|path| *path == "/api/v1/session")
            .count(),
        1
    );
    assert!(
        routes
            .iter()
            .position(|path| path == "/api/v1/session")
            .unwrap()
            < routes
                .iter()
                .position(|path| path == "/issuer/revoke")
                .unwrap()
    );
}

#[tokio::test]
async fn bootstrap_original_recovery_acquires_fresh_proof_for_the_exact_same_request() {
    let provider = Provider::start().await;
    let (directory, execution) = bootstrap_execution();
    let original = bootstrap_request();
    let script = directory.path().join("maintenance.py");
    let marker = directory.path().join("original-meaning.json");
    let original_script = std::fs::read_to_string(&script).unwrap();
    let witness = format!(
        r"
from pathlib import Path
original=Path({})
meaning={{k:v for k,v in request.items() if k!='identityProof'}}
if original.exists():
    assert json.loads(original.read_text())==meaning
else:
    original.write_text(json.dumps(meaning))
",
        serde_json::to_string(marker.to_str().unwrap()).unwrap()
    );
    std::fs::write(
        &script,
        original_script.replace(
            "assert len(request)==9",
            &format!("{witness}\nassert len(request)==9"),
        ),
    )
    .unwrap();
    for _ in 0..2 {
        let result = bootstrap(
            &provider.host(),
            &original,
            &execution,
            &mut browser(&provider),
            false,
            std::future::pending(),
        )
        .await
        .unwrap();
        assert!(matches!(
            result.maintenance.effect,
            MaintenanceEffect::Committed { .. }
        ));
        assert_eq!(result.credential_cleanup, CleanupStatus::Confirmed);
    }
    let calls = provider.state.lock().unwrap().calls.clone();
    provider.finish().await;
    assert_eq!(calls.get("/issuer/token"), Some(&2));
    assert_eq!(calls.get("/issuer/revoke"), Some(&2));
    assert_eq!(calls.get("/api/v1/session"), None);
    let retained = std::fs::read_to_string(marker).unwrap();
    assert!(!retained.contains("accessToken"));
    assert!(!retained.contains("synthetic-access-token"));
}

#[tokio::test]
async fn bootstrap_rejects_wrong_person_and_denial_before_host_submission() {
    use inframeld_cli::auth::flow::FailureKind;
    for behavior in [ProviderBehavior::WrongSubject, ProviderBehavior::Denied] {
        let provider = Provider::start().await;
        provider.state.lock().unwrap().behavior = behavior;
        let (directory, execution) = bootstrap_execution();
        let script = directory.path().join("maintenance.py");
        let marker = directory.path().join("started");
        let body = std::fs::read_to_string(&script).unwrap();
        std::fs::write(
            &script,
            format!(
                "open({},'w').write('started')\n{body}",
                serde_json::to_string(marker.to_str().unwrap()).unwrap()
            ),
        )
        .unwrap();
        let result = bootstrap(
            &provider.host(),
            &bootstrap_request(),
            &execution,
            &mut browser(&provider),
            false,
            std::future::pending(),
        )
        .await
        .unwrap_err();
        let calls = provider.state.lock().unwrap().calls.clone();
        provider.finish().await;
        assert!(!marker.exists());
        assert_eq!(calls.get("/api/v1/session"), None);
        if let ProviderBehavior::WrongSubject = behavior {
            assert_eq!(result.kind, FailureKind::Identity);
            assert_eq!(calls.get("/issuer/revoke"), Some(&1));
        } else {
            assert_eq!(result.kind, FailureKind::Denied);
            assert_eq!(calls.get("/issuer/token"), None);
        }
    }
}

#[tokio::test]
async fn bootstrap_rejects_misbound_or_repair_intent_before_discovery() {
    use inframeld_cli::auth::flow::FailureKind;
    let provider = Provider::start().await;
    let (_directory, execution) = bootstrap_execution();
    for (field, value) in [
        (
            "expectedInstallationId",
            serde_json::json!(Uuid::from_u128(99)),
        ),
        ("expectedIdentityId", serde_json::json!(Uuid::from_u128(99))),
    ] {
        let mut request: serde_json::Value = serde_json::from_slice(&bootstrap_request()).unwrap();
        request[field] = value;
        let result = bootstrap(
            &provider.host(),
            &serde_json::to_vec(&request).unwrap(),
            &execution,
            &mut browser(&provider),
            false,
            std::future::pending(),
        )
        .await
        .unwrap_err();
        assert_eq!(result.kind, FailureKind::Binding);
    }
    let result = bootstrap(
        &provider.host(),
        &request(),
        &execution,
        &mut browser(&provider),
        false,
        std::future::pending(),
    )
    .await
    .unwrap_err();
    assert_eq!(result.kind, FailureKind::InvalidRequest);
    assert!(provider.state.lock().unwrap().calls.is_empty());
    provider.finish().await;
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

#[tokio::test]
async fn recipient_diagnostic_retains_fixed_revocation_categories_without_provider_text() {
    use inframeld_cli::auth::flow::RevocationObservation;
    for (behavior, expected) in [
        (
            ProviderBehavior::AccessRevocationRejected,
            RevocationObservation::ProviderRejected,
        ),
        (
            ProviderBehavior::AccessRevocationRedirect,
            RevocationObservation::RedirectRejected,
        ),
        (
            ProviderBehavior::AccessRevocationOversize,
            RevocationObservation::ResponseTooLarge,
        ),
        (
            ProviderBehavior::AccessRevocationInvalid,
            RevocationObservation::InvalidResponse,
        ),
    ] {
        let provider = Provider::start().await;
        provider.state.lock().unwrap().behavior = behavior;
        let (_directory, execution) = execution();
        let result = repair(
            &provider.host(),
            &request(),
            &execution,
            &mut browser(&provider),
            std::future::pending(),
        )
        .await;
        let calls = provider.state.lock().unwrap().calls.clone();
        provider.finish().await;
        let result = result.unwrap();
        assert!(matches!(
            result.maintenance.effect,
            MaintenanceEffect::Committed { .. }
        ));
        assert_eq!(result.credential_cleanup, CleanupStatus::Unconfirmed);
        assert_eq!(result.credential_observations.access, expected);
        assert_eq!(
            result.credential_observations.refresh,
            RevocationObservation::NotIssued
        );
        assert_eq!(calls.get("/issuer/revoke"), Some(&1));
        assert!(!calls.keys().any(|path| path.ends_with("/unexpected")));
        assert!(!format!("{result:?}").contains("protected-provider-sentinel"));
    }
}

#[tokio::test]
async fn recipient_diagnostic_timeout_retains_the_committed_effect_and_inflight_revocation() {
    use inframeld_cli::auth::flow::RevocationObservation;
    let provider = Provider::start().await;
    provider.state.lock().unwrap().behavior = ProviderBehavior::AccessRevocationStalled;
    let (_directory, execution) = execution();
    let started = Instant::now();
    let result = repair(
        &provider.host(),
        &request(),
        &execution,
        &mut browser(&provider),
        std::future::pending(),
    )
    .await;
    let elapsed = started.elapsed();
    let calls = provider.state.lock().unwrap().calls.clone();
    provider.finish().await;
    let result = result.unwrap();
    assert!(elapsed >= Duration::from_secs(5) && elapsed < Duration::from_secs(6));
    assert!(matches!(
        result.maintenance.effect,
        MaintenanceEffect::Committed { .. }
    ));
    assert_eq!(result.credential_cleanup, CleanupStatus::Unconfirmed);
    // The existing transport also has a five-second bound. Retain whichever
    // typed observation wins that boundary, without inventing a timeout cause.
    assert!(matches!(
        result.credential_observations.access,
        RevocationObservation::TimedOut | RevocationObservation::TransportFailed
    ));
    assert_eq!(
        result.credential_observations.refresh,
        RevocationObservation::NotIssued
    );
    assert_eq!(calls.get("/issuer/revoke"), Some(&1));
}

#[tokio::test]
async fn recipient_diagnostic_refresh_rejection_does_not_restart_the_shared_cleanup_clock() {
    use inframeld_cli::auth::flow::FailureKind;
    let provider = Provider::start().await;
    provider.state.lock().unwrap().behavior = ProviderBehavior::SlowRefreshRevocationRejected;
    let (_directory, execution) = execution();
    let started = Instant::now();
    let result = repair(
        &provider.host(),
        &request(),
        &execution,
        &mut browser(&provider),
        std::future::pending(),
    )
    .await;
    let elapsed = started.elapsed();
    let calls = provider.state.lock().unwrap().calls.clone();
    provider.finish().await;
    let error = result.unwrap_err();
    assert_eq!(error.kind, FailureKind::UnexpectedRefresh);
    assert_eq!(error.credential_cleanup, CleanupStatus::Unconfirmed);
    assert_eq!(calls.get("/issuer/revoke"), Some(&2));
    assert!(elapsed >= Duration::from_secs(5) && elapsed < Duration::from_secs(6));
}

#[tokio::test]
async fn public_bootstrap_noninteractive_execution_starts_no_discovery_browser_or_claim() {
    let provider = Provider::start().await;
    let directory = tempfile::tempdir().unwrap();
    let host = directory.path().join("host.json");
    let request = directory.path().join("request.json");
    let execution = directory.path().join("execution.json");
    std::fs::write(&host,serde_json::to_vec(&serde_json::json!({"schemaVersion":1,
        "api":format!("{}/missing",provider.base),"issuer":format!("{}/issuer/",provider.base),
        "clientId":"inframeld-cli","installationId":Uuid::from_u128(1),"expectedIdentityId":Uuid::from_u128(2),
        "certificateAuthorities":[provider.ca_pem]})).unwrap()).unwrap();
    std::fs::write(&request, bootstrap_request()).unwrap();
    std::fs::write(
        &execution,
        br#"{"program":"/this-must-not-start","args":[],"environment":{}}"#,
    )
    .unwrap();
    let arguments = vec![
        "inframeld".to_owned(),
        "auth".into(),
        "bootstrap-first-administrator".into(),
        "--json".into(),
        "--no-input".into(),
        "--host-context".into(),
        host.to_str().unwrap().into(),
        "--request".into(),
        request.to_str().unwrap().into(),
        "--exec-spec".into(),
        execution.to_str().unwrap().into(),
    ];
    let (exit, output, diagnostics) = tokio::task::spawn_blocking(move || {
        let mut output = Vec::new();
        let mut diagnostics = Vec::new();
        let exit = inframeld_cli::run(arguments, &mut output, &mut diagnostics, false).unwrap();
        (exit, output, diagnostics)
    })
    .await
    .unwrap();
    let calls = provider.state.lock().unwrap().calls.clone();
    provider.finish().await;
    // Public noninteractive browser proof is rejected before all effects. The
    // existing controlled operation tests retain transport-failure coverage.
    assert_eq!(exit, 2);
    let result: serde_json::Value = serde_json::from_slice(&output).unwrap();
    assert_eq!(result.as_object().unwrap().len(), 6);
    assert_eq!(result["outcome"], "failed");
    assert_eq!(result["error"]["code"], "interaction_required");
    assert_eq!(result["data"], serde_json::Value::Null);
    assert!(calls.is_empty());
    for path in [
        "/issuer/token",
        "/issuer/authorize",
        "/api/v1/session",
        "/issuer/revoke",
    ] {
        assert_eq!(calls.get(path), None);
    }
    assert!(!String::from_utf8_lossy(&output).contains("synthetic-access-token"));
    assert!(
        String::from_utf8(diagnostics)
            .unwrap()
            .contains("interactive input")
    );
}

// Keep the same direct child and sole waiter as the executable process tests.
// Keep this one child and sole waiter together through failure and finalization.
#[allow(clippy::too_many_lines)]
fn public_tty_process(
    arguments: Vec<String>,
    state: &Mutex<State>,
    signal: Option<nix::sys::signal::Signal>,
    after_spawn: Result<(), &'static str>,
) -> Result<std::process::Output, (Vec<std::io::Error>, Option<std::process::ExitStatus>)> {
    use std::process::{Command as ProcessCommand, Stdio};
    let python = ProcessCommand::new("python3")
        .args(["-c", "import sys; print(sys.executable)"])
        .output()
        .unwrap();
    assert!(python.status.success());
    let python = String::from_utf8(python.stdout).unwrap();
    // Only fd setup precedes exec. Python is replaced, not kept as a second
    // process or waiter. The master must survive exec until this CLI exits.
    let setup = r"import os, sys
master, slave = os.openpty()
os.dup2(slave, 0, inheritable=True)
if slave != 0:
    os.close(slave)
os.set_inheritable(master, True)
os.execv(sys.argv[1], sys.argv[1:])
";
    let mut child = ProcessCommand::new(python.trim())
        .args(["-c", setup, env!("CARGO_BIN_EXE_inframeld")])
        .args(arguments)
        .env_clear()
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let cutoff = std::time::Instant::now() + Duration::from_secs(5);
    let mut sent = false;
    let mut ownership_known = true;
    let operation = (|| -> std::io::Result<()> {
        after_spawn.map_err(std::io::Error::other)?;
        loop {
            match child.try_wait() {
                Ok(Some(_)) => break,
                Ok(None) => {}
                Err(error) => {
                    ownership_known = false;
                    return Err(error);
                }
            }
            if let Some(signal) = signal
                && !sent
            {
                let ready = state
                    .lock()
                    .map_err(|_| std::io::Error::other("controlled provider state is poisoned"))?
                    .calls
                    .contains_key("/.well-known/oauth-protected-resource/missing");
                if ready {
                    let pid = i32::try_from(child.id()).map_err(std::io::Error::other)?;
                    nix::sys::signal::kill(nix::unistd::Pid::from_raw(pid), signal)
                        .map_err(|error| std::io::Error::from_raw_os_error(error as i32))?;
                    sent = true;
                }
            }
            if std::time::Instant::now() >= cutoff {
                return Err(std::io::Error::other(
                    "the controlled public child exceeded its existing test wait",
                ));
            }
            std::thread::sleep(Duration::from_millis(5));
        }
        if signal.is_some() && !sent {
            return Err(std::io::Error::other(
                "the controlled signal boundary was not reached",
            ));
        }
        Ok(())
    })();
    let mut errors: Vec<_> = operation.err().into_iter().collect();
    // No assertion can unwind past this owner. An uncertain wait never grants
    // permission to signal a numeric PID that may no longer be ours.
    let killed = !errors.is_empty()
        && ownership_known
        && child.kill().map_err(|error| errors.push(error)).is_ok();
    let waited = if !ownership_known {
        None
    } else if !errors.is_empty() && !killed {
        child
            .try_wait()
            .map_err(|error| errors.push(error))
            .ok()
            .flatten()
    } else {
        child.wait().map_err(|error| errors.push(error)).ok()
    };
    // These scenarios finish before browser dispatch, so no descendant can
    // retain the pipes. Wait/reap completes before bounded-output assertions.
    let output = if waited.is_some() {
        child
            .wait_with_output()
            .map_err(|error| errors.push(error))
            .ok()
    } else {
        errors.push(std::io::Error::other("owned child cleanup is unconfirmed"));
        None
    };
    if output
        .as_ref()
        .is_some_and(|output| output.stdout.len() > 16_384 || output.stderr.len() > 4_096)
    {
        errors.push(std::io::Error::other(
            "the controlled public output exceeded its existing bound",
        ));
    }
    match output {
        Some(output) if errors.is_empty() => Ok(output),
        _ => Err((errors, waited)),
    }
}

#[tokio::test]
async fn real_public_tty_entry_and_signals_preserve_policy_and_fixed_outcomes() {
    use nix::sys::signal::Signal;
    for (signal, no_input, expected) in [
        (None, false, 1),
        (None, true, 2),
        (Some(Signal::SIGINT), false, 130),
        (Some(Signal::SIGTERM), false, 143),
    ] {
        let provider = Provider::start().await;
        if signal.is_some() {
            provider.state.lock().unwrap().behavior = ProviderBehavior::DiscoveryStalled;
        }
        let directory = tempfile::tempdir().unwrap();
        let host = directory.path().join("host.json");
        let request = directory.path().join("request.json");
        let execution = directory.path().join("execution.json");
        std::fs::write(&host,serde_json::to_vec(&serde_json::json!({"schemaVersion":1,
            "api":format!("{}/missing",provider.base),"issuer":format!("{}/issuer/",provider.base),
            "clientId":"inframeld-cli","installationId":Uuid::from_u128(1),"expectedIdentityId":Uuid::from_u128(2),
            "certificateAuthorities":[provider.ca_pem]})).unwrap()).unwrap();
        std::fs::write(&request, bootstrap_request()).unwrap();
        std::fs::write(
            &execution,
            br#"{"program":"/must-not-start","args":[],"environment":{}}"#,
        )
        .unwrap();
        let mut arguments = vec![
            "auth".into(),
            "bootstrap-first-administrator".into(),
            "--json".into(),
            "--host-context".into(),
            host.to_str().unwrap().into(),
            "--request".into(),
            request.to_str().unwrap().into(),
            "--exec-spec".into(),
            execution.to_str().unwrap().into(),
        ];
        if no_input {
            arguments.push("--no-input".into());
        }
        let state = provider.state.clone();
        let output = tokio::task::spawn_blocking(move || {
            public_tty_process(arguments, &state, signal, Ok(()))
        })
        .await
        .unwrap()
        .unwrap();
        let calls = provider.state.lock().unwrap().calls.clone();
        provider.finish().await;
        assert_eq!(output.status.code(), Some(expected));
        let result: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(result.as_object().unwrap().len(), 6);
        if no_input {
            assert_eq!(result["error"]["code"], "interaction_required");
            assert!(calls.is_empty());
        } else {
            assert_eq!(
                calls.get("/.well-known/oauth-protected-resource/missing"),
                Some(&1)
            );
            if signal.is_some() {
                assert_eq!(result["outcome"], "interrupted");
                assert_eq!(result["data"]["kind"], "cancelled");
            } else {
                assert_eq!(result["data"]["kind"], "discovery");
            }
            assert_eq!(result["data"]["resourceCleanup"], "not-needed");
            assert_eq!(result["data"]["credentialCleanup"], "not-needed");
        }
        for path in [
            "/issuer/token",
            "/issuer/authorize",
            "/api/v1/session",
            "/issuer/revoke",
        ] {
            assert_eq!(calls.get(path), None);
        }
        assert!(!String::from_utf8_lossy(&output.stdout).contains("synthetic-access-token"));
    }
}

#[tokio::test]
async fn public_tty_child_is_finalized_before_reporting_controlled_failure() {
    use std::os::unix::process::ExitStatusExt as _;
    let provider = Provider::start().await;
    let state = provider.state.clone();
    let result = tokio::task::spawn_blocking(move || {
        public_tty_process(
            vec!["version".into()],
            &state,
            None,
            Err("controlled after-spawn failure"),
        )
    })
    .await
    .unwrap();
    provider.finish().await;
    let (errors, status) = result.unwrap_err();
    assert_eq!(
        errors.first().map(ToString::to_string),
        Some("controlled after-spawn failure".into())
    );
    let status = status.unwrap();
    assert!(status.success() || status.signal() == Some(nix::libc::SIGKILL));
}
