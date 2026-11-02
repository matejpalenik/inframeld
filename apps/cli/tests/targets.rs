//! Exercise the executable's credential-free target and saved-selection contract.
#![allow(clippy::unwrap_used, clippy::expect_used)]

use assert_cmd::Command;
use serde_json::{Value, json};
use std::{fs, os::unix::fs::PermissionsExt, process::Output, time::Duration};
use tempfile::TempDir;

fn command(home: &TempDir) -> Command {
    let mut command = Command::new(assert_cmd::cargo::cargo_bin!("inframeld"));
    command
        .env_clear()
        .env("HOME", home.path())
        .env("PATH", "")
        .current_dir(home.path())
        .timeout(Duration::from_secs(15));
    command
}

fn invoke(home: &TempDir, arguments: &[&str], environment: Option<&str>) -> Output {
    let mut command = command(home);
    command.args(arguments);
    if let Some(target) = environment {
        command.env("INFRAMELD_TARGET", target);
    }
    command.output().unwrap()
}

fn result(output: &Output) -> Value {
    serde_json::from_slice(&output.stdout).unwrap()
}

fn seed(home: &TempDir) {
    let path = home.path().join(".config/inframeld");
    fs::create_dir_all(&path).unwrap();
    fs::set_permissions(&path, fs::Permissions::from_mode(0o700)).unwrap();
    let binding = |label| {
        json!({"label":label,"installationId":"00000000-0000-0000-0000-00000000002a",
        "apiUrl":"https://api.example.test/api/v1","issuerUrl":"https://identity.example.test",
        "clientId":"inframeld-cli","transport":{"caFiles":[],"proxy":null}})
    };
    fs::write(
        path.join("targets"),
        serde_json::to_vec(&json!({"schemaVersion":1,"selectedTarget":"prod",
        "targets":{"dev":binding("dev"),"prod":binding("prod")}}))
        .unwrap(),
    )
    .unwrap();
    fs::set_permissions(path.join("targets"), fs::Permissions::from_mode(0o600)).unwrap();
}

#[test]
fn nested_target_help_is_complete_and_never_loads_user_state() {
    let home = TempDir::new().unwrap();
    let output = invoke(
        &home,
        &["target", "add", "--help", "--json", "--unknown"],
        None,
    );
    assert!(output.status.success());
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(text.contains("Usage: inframeld target add"));
    assert!(text.contains("--ca-cert") && text.contains("--proxy") && text.contains("--no-input"));
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn missing_target_has_a_safe_machine_failure_without_creating_state() {
    let home = TempDir::new().unwrap();
    let output = invoke(&home, &["target", "show", "--json", "--no-input"], None);
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(result(&output)["error"]["code"], "target_not_found");
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn effective_override_is_ephemeral_and_explicit_use_reports_environment_override() {
    let home = TempDir::new().unwrap();
    seed(&home);
    let path = home.path().join(".config/inframeld/targets");
    let before = fs::read(&path).unwrap();
    let output = invoke(
        &home,
        &["--target", "dev", "target", "show", "--json"],
        Some("invalid url"),
    );
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(result(&output)["data"]["target"]["label"], "dev");
    assert_eq!(result(&output)["data"]["source"], "flag");
    assert_eq!(fs::read(&path).unwrap(), before);
    let output = invoke(&home, &["target", "use", "dev", "--json"], Some("prod"));
    assert!(output.status.success());
    assert_eq!(result(&output)["data"]["savedTarget"], "dev");
    assert_eq!(result(&output)["data"]["effectiveTarget"], "prod");
    assert_eq!(
        result(&output)["warnings"][0]["code"],
        "environment_overrides_saved_target"
    );
    assert_eq!(
        result(&invoke(&home, &["target", "show", "--json"], None))["data"]["target"]["label"],
        "dev"
    );
}

#[test]
fn registration_dry_run_needs_no_server_and_changes_no_configuration() {
    let home = TempDir::new().unwrap();
    let output = invoke(
        &home,
        &[
            "target",
            "add",
            "dev",
            "--url",
            "https://127.0.0.1:9/api/v1",
            "--dry-run",
            "--json",
            "--no-input",
        ],
        None,
    );
    assert!(output.status.success());
    let object = result(&output);
    assert_eq!(object["mode"], "dryRun");
    assert_eq!(object["data"]["remoteVerification"], "notPerformed");
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn human_show_preview_preserves_effective_context_without_writing_state() {
    let home = TempDir::new().unwrap();
    seed(&home);
    let path = home.path().join(".config/inframeld/targets");
    let before = fs::read(&path).unwrap();
    for (environment, target, source) in
        [(None, "prod", "Saved"), (Some("dev"), "dev", "Environment")]
    {
        let output = invoke(&home, &["target", "show", "--dry-run"], environment);
        assert!(output.status.success());
        let text = String::from_utf8(output.stdout).unwrap();
        assert!(
            text.contains(&format!("Effective target: {target}")),
            "{text}"
        );
        assert!(text.contains(&format!("Source: {source}")), "{text}");
        assert!(text.contains("Remote verification: not performed"));
        assert_eq!(fs::read(&path).unwrap(), before);
        assert_eq!(fs::read_dir(path.parent().unwrap()).unwrap().count(), 1);
    }
}

#[test]
fn change_views_preview_the_observed_preference_without_writing_it() {
    for preference in [Some("prod"), None] {
        let home = TempDir::new().unwrap();
        seed(&home);
        let path = home.path().join(".config/inframeld/targets");
        let mut state: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        state["selectedTarget"] = json!(preference);
        fs::write(&path, serde_json::to_vec(&state).unwrap()).unwrap();
        let before = fs::read(&path).unwrap();
        for format in ["--json", "--jsonl"] {
            let output = invoke(&home, &["target", "use", "dev", "--dry-run", format], None);
            assert!(output.status.success());
            let object = result(&output);
            let object = if format == "--jsonl" {
                &object["result"]
            } else {
                &object
            };
            assert_eq!(object["mode"], "dryRun");
            assert_eq!(
                object["data"]["changes"],
                json!([{
                    "kind":"proposed", "resource":{"kind":"targetPreference"},
                    "fields":[{"field":"savedTarget", "before":{"known":true,"value":preference},
                        "after":{"known":true,"value":"dev"}}]
                }])
            );
            assert_eq!(object["data"]["outgoingDataCategories"], json!([]));
            assert_eq!(
                object["data"]["destinations"],
                json!([{"kind":"localTargetRegistry"}])
            );
            assert_eq!(object["data"]["remoteVerification"], "notPerformed");
        }
        let output = invoke(
            &home,
            &["target", "use", "dev", "--dry-run", "--plain", "--no-color"],
            None,
        );
        assert!(output.status.success());
        let text = String::from_utf8(output.stdout).unwrap();
        assert!(text.contains("Current / Proposed"), "{text}");
        assert!(text.contains("Saved target"), "{text}");
        assert!(
            text.contains(preference.unwrap_or("not selected")),
            "{text}"
        );
        assert!(text.contains("dev") && !text.contains('\u{1b}'));
        assert_eq!(fs::read(&path).unwrap(), before);
        assert_eq!(fs::read_dir(path.parent().unwrap()).unwrap().count(), 1);
    }
}

#[test]
fn change_views_confirm_only_the_saved_change_and_keep_an_override_separate() {
    let home = TempDir::new().unwrap();
    seed(&home);
    let output = invoke(&home, &["target", "use", "dev", "--json"], Some("prod"));
    assert!(output.status.success());
    let object = result(&output);
    assert_eq!(
        object["data"]["changes"],
        json!([{
            "kind":"confirmed", "resource":{"kind":"targetPreference"},
            "fields":[{"field":"savedTarget", "before":{"known":true,"value":"prod"},
                "after":{"known":true,"value":"dev"}}]
        }])
    );
    assert_eq!(object["data"]["savedTarget"], "dev");
    assert_eq!(object["data"]["effectiveTarget"], "prod");
    assert_eq!(object["data"]["source"], "environment");
    assert_eq!(
        object["warnings"][0]["code"],
        "environment_overrides_saved_target"
    );
    let repeated = invoke(&home, &["target", "use", "dev", "--json"], None);
    assert_eq!(result(&repeated)["data"]["saveStatus"], "unchanged");
    assert_eq!(result(&repeated)["data"]["changes"], json!([]));
    let unchanged = invoke(&home, &["target", "use", "dev"], None);
    let text = String::from_utf8(unchanged.stdout).unwrap();
    assert!(text.contains("unchanged"), "{text}");
    assert!(!text.contains("Before / Now"));
    let changed = invoke(&home, &["target", "use", "prod", "--plain"], None);
    let text = String::from_utf8(changed.stdout).unwrap();
    assert!(text.contains("Before / Now"), "{text}");
    assert!(text.contains("dev") && text.contains("prod"));
}

#[test]
fn change_views_preview_shell_overrides_without_claiming_a_save_or_fallback() {
    let home = TempDir::new().unwrap();
    seed(&home);
    let path = home.path().join(".config/inframeld/targets");
    let before = fs::read(&path).unwrap();
    for environment in ["prod", "missing", "unsafe\u{1b}input"] {
        let output = invoke(
            &home,
            &["target", "use", "dev", "--dry-run", "--json"],
            Some(environment),
        );
        assert!(output.status.success());
        let object = result(&output);
        assert_eq!(object["data"]["source"], "environment");
        assert_eq!(
            object["warnings"][0]["code"],
            "environment_overrides_saved_target"
        );
        if environment == "prod" {
            assert_eq!(object["data"]["effectiveTarget"], "prod");
        } else {
            assert_eq!(object["data"]["effectiveTarget"], Value::Null);
            assert_eq!(object["warnings"][1]["code"], "effective_target_unresolved");
            assert!(
                object["data"]["unresolvedFacts"]
                    .as_array()
                    .unwrap()
                    .contains(&json!("effectiveTargetUnresolved"))
            );
        }
        assert!(!String::from_utf8_lossy(&output.stdout).contains("unsafe"));
        assert_eq!(fs::read(&path).unwrap(), before);
        assert_eq!(fs::read_dir(path.parent().unwrap()).unwrap().count(), 1);
    }
}

#[test]
fn change_views_registration_preview_discloses_destinations_and_actual_unknowns() {
    let home = TempDir::new().unwrap();
    let arguments = [
        "target",
        "add",
        "dev",
        "--url",
        "https://127.0.0.1:9/api/v1",
        "--proxy",
        "http://proxy.example.test:8080",
        "--dry-run",
    ];
    let mut machine = arguments.to_vec();
    machine.push("--json");
    let output = invoke(&home, &machine, None);
    assert!(output.status.success());
    let data = &result(&output)["data"];
    assert_eq!(
        data["outgoingDataCategories"],
        json!(["publicApiIdentity", "httpRequestMetadata"])
    );
    assert_eq!(
        data["destinations"],
        json!([
            {"kind":"localTargetRegistry"},
            {"kind":"api","url":{"known":true,"value":"https://127.0.0.1:9/api/v1"}},
            {"kind":"issuerMetadata","url":{"known":false}},
            {"kind":"issuerKeySet","url":{"known":false}},
            {"kind":"proxy","url":{"known":true,"value":"http://proxy.example.test:8080"}}
        ])
    );
    assert_eq!(
        data["unresolvedFacts"],
        json!([
            "remoteIdentityUnverified",
            "providerDestinationsUnresolved",
            "persistenceNotPerformed"
        ])
    );
    let output = invoke(&home, &arguments, None);
    let text = String::from_utf8(output.stdout).unwrap();
    for fact in [
        "public API identity",
        "HTTP request metadata",
        "issuer metadata",
        "issuer key set",
        "unknown",
        "proxy.example.test",
        "save not performed",
    ] {
        assert!(text.contains(fact), "{text}");
    }
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn change_views_read_preview_labels_cached_scope_and_sends_nothing() {
    let home = TempDir::new().unwrap();
    seed(&home);
    let output = invoke(&home, &["target", "show", "--dry-run", "--json"], None);
    assert!(output.status.success());
    let data = &result(&output)["data"];
    assert_eq!(data["outgoingDataCategories"], json!([]));
    assert_eq!(
        data["destinations"],
        json!([{"kind":"localTargetRegistry"}])
    );
    assert_eq!(data["unresolvedFacts"], json!(["remoteHealthUnverified"]));
    assert_eq!(data["changes"], json!([]));
}

#[test]
fn change_views_identical_proposal_is_explicitly_unchanged_and_still_unsaved() {
    let home = TempDir::new().unwrap();
    seed(&home);
    let path = home.path().join(".config/inframeld/targets");
    let before = fs::read(&path).unwrap();
    let output = invoke(&home, &["target", "use", "prod", "--dry-run"], None);
    assert!(output.status.success());
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(text.contains("Current / Proposed"));
    assert!(text.contains("unchanged"), "{text}");
    assert!(text.contains("save not performed"));
    assert!(!text.contains("Before / Now"));
    assert_eq!(fs::read(&path).unwrap(), before);
}

#[test]
fn captured_previews_stay_plain_and_machine_equivalent_even_when_color_is_forced() {
    let home = TempDir::new().unwrap();
    seed(&home);
    let path = home.path().join(".config/inframeld/targets");
    let before = fs::read(&path).unwrap();
    let expected = result(&invoke(
        &home,
        &["target", "use", "dev", "--dry-run", "--json"],
        None,
    ));
    for flags in [&[][..], &["--plain"][..], &["--no-color"][..]] {
        for environment in [
            None,
            Some(("NO_COLOR", "1")),
            Some(("NO_COLOR", "")),
            Some(("TERM", "dumb")),
        ] {
            for format in [None, Some("--json"), Some("--jsonl")] {
                let mut child = command(&home);
                child
                    .args(["target", "use", "dev", "--dry-run"])
                    .args(flags)
                    .env("TERM", "xterm-256color")
                    .env("CLICOLOR_FORCE", "1");
                if let Some((name, value)) = environment {
                    child.env(name, value);
                }
                if let Some(format) = format {
                    child.arg(format);
                }
                let output = child.output().unwrap();
                assert!(
                    output.status.success(),
                    "{}",
                    String::from_utf8_lossy(&output.stderr)
                );
                assert!(!output.stdout.contains(&0x1b));
                assert!(!output.stderr.contains(&0x1b));
                if let Some(format) = format {
                    let value = result(&output);
                    let object = if format == "--jsonl" {
                        &value["result"]
                    } else {
                        &value
                    };
                    assert_eq!(object, &expected);
                } else {
                    let text = String::from_utf8(output.stdout).unwrap();
                    assert!(text.contains("Current / Proposed"));
                    assert!(text.contains("  Current: prod\n  -> Proposed: dev\n"));
                    assert!(text.contains("Remote verification: not performed"));
                }
                assert_eq!(fs::read(&path).unwrap(), before);
                assert_eq!(fs::read_dir(path.parent().unwrap()).unwrap().count(), 1);
            }
        }
    }
}

#[test]
fn terminal_controls_in_saved_labels_never_reach_output_or_rewrite_state() {
    let home = TempDir::new().unwrap();
    seed(&home);
    let path = home.path().join(".config/inframeld/targets");
    let mut state: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
    state["targets"]["dev"]["label"] = json!("dev\u{1b}]2;forged-title\u{7}");
    fs::write(&path, serde_json::to_vec(&state).unwrap()).unwrap();
    let before = fs::read(&path).unwrap();
    for format in [None, Some("--json"), Some("--jsonl")] {
        let mut child = command(&home);
        child
            .args(["target", "use", "dev", "--dry-run"])
            .env("CLICOLOR_FORCE", "1")
            .env("TERM", "xterm-256color");
        if let Some(format) = format {
            child.arg(format);
        }
        let output = child.output().unwrap();
        assert_eq!(output.status.code(), Some(1));
        assert!(!output.stdout.contains(&0x1b) && !output.stderr.contains(&0x1b));
        assert!(!output.stdout.contains(&0x7) && !output.stderr.contains(&0x7));
        assert!(!String::from_utf8_lossy(&output.stdout).contains("forged-title"));
        assert!(!String::from_utf8_lossy(&output.stderr).contains("forged-title"));
        assert_eq!(fs::read(&path).unwrap(), before);
    }
}

#[test]
fn credential_bearing_proxy_is_rejected_without_echoing_it_or_saving_state() {
    let home = TempDir::new().unwrap();
    let output = invoke(
        &home,
        &[
            "target",
            "add",
            "dev",
            "--url",
            "https://127.0.0.1:9",
            "--proxy",
            "http://user:private-sentinel@127.0.0.1:9",
            "--json",
        ],
        None,
    );
    assert_eq!(result(&output)["error"]["code"], "invalid_proxy_url");
    assert!(!String::from_utf8_lossy(&output.stdout).contains("private-sentinel"));
    assert!(!String::from_utf8_lossy(&output.stderr).contains("private-sentinel"));
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn remote_input_cannot_claim_the_managed_local_http_exception() {
    let home = TempDir::new().unwrap();
    for url in [
        "http://127.0.0.1:9",
        "not-a-url",
        "https://private-sentinel@api.example.test",
    ] {
        for format in [None, Some("--json"), Some("--jsonl")] {
            for dry_run in [false, true] {
                let mut arguments = vec!["target", "add", "local", "--url", url];
                arguments.extend(format);
                if dry_run {
                    arguments.push("--dry-run");
                }
                let output = invoke(&home, &arguments, None);
                assert_eq!(
                    output.status.code(),
                    Some(2),
                    "{url} {format:?} dry-run={dry_run}"
                );
                let object = match format {
                    Some("--jsonl") => Some(result(&output)["result"].clone()),
                    Some(_) => Some(result(&output)),
                    None => None,
                };
                if let Some(object) = object {
                    assert_eq!(object["error"]["code"], "discovery_invalid_url");
                    assert_eq!(object["outcome"], "failed");
                }
                assert!(!String::from_utf8_lossy(&output.stdout).contains("private-sentinel"));
                assert!(!String::from_utf8_lossy(&output.stderr).contains("private-sentinel"));
                assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
            }
        }
    }
}

/// Only public discovery metadata and synthetic verification keys are served.
struct DiscoveryFixture {
    url: String,
    pem: String,
    requests: std::sync::Arc<std::sync::Mutex<Vec<String>>>,
    task: tokio::task::JoinHandle<()>,
}

impl Drop for DiscoveryFixture {
    fn drop(&mut self) {
        self.task.abort();
    }
}

async fn discovery_fixture(stall: bool, invalid_provider_url: bool) -> DiscoveryFixture {
    use std::sync::{Arc, Mutex};
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        net::TcpListener,
        task::JoinSet,
    };
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let url = format!("https://{}", listener.local_addr().unwrap());
    let params = rcgen::CertificateParams::new(vec!["127.0.0.1".into()]).unwrap();
    let key = rcgen::KeyPair::generate().unwrap();
    let certificate = params.self_signed(&key).unwrap();
    let pem = certificate.pem();
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
    let acceptor = tokio_rustls::TlsAcceptor::from(Arc::new(config));
    let requests = Arc::new(Mutex::new(Vec::new()));
    let (base, observed) = (url.clone(), requests.clone());
    let task = tokio::spawn(async move {
        let mut children = JoinSet::new();
        loop {
            tokio::select! {
                accepted = listener.accept() => {
                    let (socket, _) = accepted.unwrap();
                    let (base, observed, acceptor) = (base.clone(), observed.clone(), acceptor.clone());
                    children.spawn(async move {
                        let Ok(mut socket) = acceptor.accept(socket).await else { return };
                        let mut request = Vec::new();
                        while !request.ends_with(b"\r\n\r\n") {
                            let mut byte = [0];
                            if socket.read_exact(&mut byte).await.is_err() { return }
                            request.push(byte[0]);
                            assert!(request.len() <= 32 * 1024);
                        }
                        let request = String::from_utf8(request).unwrap();
                        let path = request.split_whitespace().nth(1).unwrap().to_owned();
                        observed.lock().unwrap().push(request);
                        if stall { std::future::pending::<()>().await; }
                        let issuer = format!("{base}/issuer/");
                        let keys = if invalid_provider_url { format!("{issuer}keys?invalid") } else { format!("{issuer}keys") };
                        let body = match path.as_str() {
                            "/.well-known/oauth-protected-resource/api/v1" => json!({"resource":format!("{base}/api/v1"),"authorization_servers":[issuer],"scopes_supported":["inframeld:api"],"bearer_methods_supported":["header"],"inframeld":{"installation_id":"00000000-0000-0000-0000-00000000002a","client_id":"inframeld-cli","schema_version":1}}),
                            "/issuer/.well-known/openid-configuration" => json!({"issuer":issuer,"authorization_endpoint":format!("{issuer}authorize"),"token_endpoint":format!("{issuer}token"),"jwks_uri":keys,"grant_types_supported":["authorization_code","refresh_token"],"response_types_supported":["code"],"token_endpoint_auth_methods_supported":["none"],"subject_types_supported":["public"],"id_token_signing_alg_values_supported":["RS256"],"code_challenge_methods_supported":["S256"]}),
                            "/issuer/keys" => json!({"keys":[{"kty":"RSA","kid":"test","use":"sig","alg":"RS256","n":"AQAB","e":"AQAB"}]}),
                            _ => json!({"unexpected":true}),
                        }.to_string();
                        let response = format!("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{body}", body.len());
                        let _ = socket.write_all(response.as_bytes()).await;
                        let _ = socket.shutdown().await;
                    });
                }
                completed = children.join_next(), if !children.is_empty() => { completed.unwrap().unwrap(); }
            }
        }
    });
    DiscoveryFixture {
        url,
        pem,
        requests,
        task,
    }
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn human_registration_preview_shows_known_destination_without_discovery_or_saving() {
    let server = discovery_fixture(false, false).await;
    let home = TempDir::new().unwrap();
    let api = format!("{}/api/v1", server.url);
    let output = invoke(
        &home,
        &["target", "add", "dev", "--url", &api, "--dry-run"],
        None,
    );
    assert!(output.status.success());
    let text = String::from_utf8(output.stdout).unwrap();
    assert!(text.contains(&format!("API: {api}")), "{text}");
    assert!(text.contains("Requested target: dev"));
    assert!(text.contains("Remote verification: not performed"));
    assert!(server.requests.lock().unwrap().is_empty());
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn invalid_provider_url_after_dispatch_remains_an_operational_failure() {
    let server = discovery_fixture(false, true).await;
    let home = TempDir::new().unwrap();
    let certificates = TempDir::new().unwrap();
    let ca = certificates.path().join("operator.pem");
    fs::write(&ca, &server.pem).unwrap();
    let api = format!("{}/api/v1", server.url);
    let output = invoke(
        &home,
        &[
            "target",
            "add",
            "dev",
            "--url",
            &api,
            "--ca-cert",
            ca.to_str().unwrap(),
            "--json",
        ],
        None,
    );
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(result(&output)["error"]["code"], "discovery_invalid_url");
    assert!(server.requests.lock().unwrap().len() >= 2);
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn public_https_registration_saves_only_the_validated_binding_then_selection_is_explicit() {
    let server = discovery_fixture(false, false).await;
    let home = TempDir::new().unwrap();
    let certificates = TempDir::new().unwrap();
    let ca = certificates.path().join("operator.pem");
    fs::write(&ca, &server.pem).unwrap();
    let api = format!("{}/api/v1", server.url);
    let arguments = [
        "target",
        "add",
        "dev",
        "--url",
        api.as_str(),
        "--ca-cert",
        ca.to_str().unwrap(),
        "--json",
        "--no-input",
    ];
    let output = command(&home)
        .args(arguments)
        .env("HTTP_PROXY", "http://private-proxy-marker@127.0.0.1:9")
        .env("HTTPS_PROXY", "http://private-proxy-marker@127.0.0.1:9")
        .env("ALL_PROXY", "http://private-proxy-marker@127.0.0.1:9")
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "{}",
        String::from_utf8_lossy(&output.stderr)
    );
    let object = result(&output);
    assert_eq!(object["data"]["registration"], "saved");
    assert_eq!(object["data"]["target"]["apiUrl"], api);
    assert_eq!(object["data"]["selectionChanged"], false);
    let state: Value =
        serde_json::from_slice(&fs::read(home.path().join(".config/inframeld/targets")).unwrap())
            .unwrap();
    assert_eq!(state["selectedTarget"], Value::Null);
    assert_eq!(state["targets"]["dev"]["transport"]["caFiles"], json!([ca]));
    assert!(!state.to_string().contains("BEGIN CERTIFICATE"));
    assert_eq!(server.requests.lock().unwrap().len(), 3);
    assert!(server.requests.lock().unwrap().iter().all(|request| {
        let lower = request.to_ascii_lowercase();
        !lower.contains("authorization:") && !lower.contains("cookie:")
    }));
    let output = invoke(&home, &arguments, None);
    assert_eq!(result(&output)["data"]["registration"], "alreadyRegistered");
    let output = invoke(&home, &["target", "use", "dev", "--json"], None);
    assert!(output.status.success());
    let before = fs::read(home.path().join(".config/inframeld/targets")).unwrap();
    let replacement = rcgen::generate_simple_self_signed(vec!["127.0.0.1".into()]).unwrap();
    fs::write(&ca, replacement.cert.pem()).unwrap();
    let changed = invoke(&home, &arguments, None);
    assert_eq!(result(&changed)["error"]["code"], "discovery_tls");
    assert_eq!(server.requests.lock().unwrap().len(), 6);
    fs::write(&ca, "invalid current operator CA").unwrap();
    // Preference/readback does not imply transport health or read a live CA file.
    assert!(
        invoke(&home, &["target", "show", "--json"], None)
            .status
            .success()
    );
    let rejected = invoke(&home, &arguments, None);
    assert_eq!(result(&rejected)["error"]["code"], "invalid_ca_file");
    assert_eq!(
        fs::read(home.path().join(".config/inframeld/targets")).unwrap(),
        before
    );
    assert_eq!(server.requests.lock().unwrap().len(), 6);
}

/// This fixture owns one CLI process and reaps it before a deadline assertion can fail.
struct RunningCli(Option<std::process::Child>);

impl RunningCli {
    async fn finish_or_kill(&mut self, timeout: Duration) -> (Output, bool) {
        let deadline = std::time::Instant::now() + timeout;
        loop {
            if self.0.as_mut().unwrap().try_wait().unwrap().is_some() {
                return (self.0.take().unwrap().wait_with_output().unwrap(), true);
            }
            if std::time::Instant::now() >= deadline {
                let mut child = self.0.take().unwrap();
                child.kill().unwrap();
                return (child.wait_with_output().unwrap(), false);
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    }

    #[allow(clippy::panic)]
    async fn finish(mut self) -> Output {
        let deadline = std::time::Instant::now() + Duration::from_secs(5);
        loop {
            if self.0.as_mut().unwrap().try_wait().unwrap().is_some() {
                return self.0.take().unwrap().wait_with_output().unwrap();
            }
            if std::time::Instant::now() >= deadline {
                let mut child = self.0.take().unwrap();
                child.kill().unwrap();
                let output = child.wait_with_output().unwrap();
                panic!("CLI interruption exceeded its deadline after owned cleanup: {output:?}");
            }
            tokio::time::sleep(Duration::from_millis(10)).await;
        }
    }
}

impl Drop for RunningCli {
    fn drop(&mut self) {
        if let Some(mut child) = self.0.take() {
            if child.try_wait().unwrap().is_none() {
                let _ = child.kill();
            }
            let _ = child.wait();
        }
    }
}

async fn interrupted_registration(signal: &str, expected: i32) {
    use std::process::{Command as ProcessCommand, Stdio};
    let server = discovery_fixture(true, false).await;
    let home = TempDir::new().unwrap();
    let certificates = TempDir::new().unwrap();
    let ca = certificates.path().join("operator.pem");
    fs::write(&ca, &server.pem).unwrap();
    let api = format!("{}/api/v1", server.url);
    let child = ProcessCommand::new(assert_cmd::cargo::cargo_bin!("inframeld"))
        .args([
            "target",
            "add",
            "dev",
            "--url",
            &api,
            "--ca-cert",
            ca.to_str().unwrap(),
            "--json",
            "--no-input",
        ])
        .env_clear()
        .env("HOME", home.path())
        .env("PATH", "")
        .current_dir(home.path())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut child = RunningCli(Some(child));
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    while server.requests.lock().unwrap().is_empty() {
        assert!(
            child.0.as_mut().unwrap().try_wait().unwrap().is_none(),
            "CLI ended before discovery"
        );
        assert!(
            std::time::Instant::now() < deadline,
            "CLI did not reach the owned public metadata server"
        );
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    // The unreaped owned child retains its PID through this one explicit signal.
    assert!(
        ProcessCommand::new("/bin/kill")
            .args([
                &format!("-{signal}"),
                &child.0.as_ref().unwrap().id().to_string()
            ])
            .status()
            .unwrap()
            .success()
    );
    let output = child.finish().await;
    assert_eq!(output.status.code(), Some(expected));
    assert_eq!(result(&output)["outcome"], "interrupted");
    assert_eq!(result(&output)["error"]["code"], "target_interrupted");
    assert_eq!(server.requests.lock().unwrap().len(), 1);
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn interrupt_during_discovery_reports_no_saved_target_without_retry() {
    interrupted_registration("INT", 130).await;
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn termination_during_discovery_reports_interruption_without_cancellation_claim() {
    interrupted_registration("TERM", 143).await;
}

/// Own a finite pipe filler until the test drains and joins it after child cleanup.
fn prefilled_pipe() -> (
    std::io::PipeReader,
    std::io::PipeWriter,
    std::thread::JoinHandle<()>,
) {
    use std::io::Write;
    let (reader, mut filler) = std::io::pipe().unwrap();
    let stdout = filler.try_clone().unwrap();
    let (started, ready) = std::sync::mpsc::channel();
    let fill = std::thread::spawn(move || {
        for index in 0..512 {
            if filler.write_all(&[b'x'; 4096]).is_err() {
                break;
            }
            if index == 0 {
                let _ = started.send(());
            }
        }
    });
    ready.recv_timeout(Duration::from_secs(2)).unwrap();
    (reader, stdout, fill)
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn second_interrupt_can_exit_while_the_final_machine_pipe_is_blocked() {
    use std::{
        io::{BufRead, Read},
        process::{Command as ProcessCommand, Stdio},
    };
    let server = discovery_fixture(true, false).await;
    let home = TempDir::new().unwrap();
    let certificates = TempDir::new().unwrap();
    let ca = certificates.path().join("operator.pem");
    fs::write(&ca, &server.pem).unwrap();
    let (mut reader, stdout, fill) = prefilled_pipe();
    let api = format!("{}/api/v1", server.url);
    let mut child = ProcessCommand::new(assert_cmd::cargo::cargo_bin!("inframeld"))
        .args([
            "target",
            "add",
            "dev",
            "--url",
            &api,
            "--ca-cert",
            ca.to_str().unwrap(),
            "--json",
            "--no-input",
        ])
        .env_clear()
        .env("HOME", home.path())
        .env("PATH", "")
        .current_dir(home.path())
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let stderr = child.stderr.take().unwrap();
    let (ready, notification) = std::sync::mpsc::channel();
    let diagnostic = std::thread::spawn(move || {
        let mut text = String::new();
        for line in std::io::BufReader::new(stderr).lines() {
            let line = line.unwrap();
            if line.contains("error: The target command was interrupted") {
                let _ = ready.send(());
            }
            text.push_str(&line);
        }
        text
    });
    let mut child = RunningCli(Some(child));
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    while server.requests.lock().unwrap().is_empty() {
        assert!(std::time::Instant::now() < deadline);
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    assert!(
        ProcessCommand::new("/bin/kill")
            .args(["-INT", &child.0.as_ref().unwrap().id().to_string()])
            .status()
            .unwrap()
            .success()
    );
    notification.recv_timeout(Duration::from_secs(3)).unwrap();
    assert!(child.0.as_mut().unwrap().try_wait().unwrap().is_none());
    assert!(
        ProcessCommand::new("/bin/kill")
            .args(["-INT", &child.0.as_ref().unwrap().id().to_string()])
            .status()
            .unwrap()
            .success()
    );
    let deadline = std::time::Instant::now() + Duration::from_secs(2);
    let mut stopped = None;
    while std::time::Instant::now() < deadline {
        stopped = child.0.as_mut().unwrap().try_wait().unwrap();
        if stopped.is_some() {
            break;
        }
        tokio::time::sleep(Duration::from_millis(10)).await;
    }
    if stopped.is_none() {
        child.0.as_mut().unwrap().kill().unwrap();
    }
    let output = child.0.take().unwrap().wait_with_output().unwrap();
    // Reap the child before draining and joining both finite fixture threads.
    let mut drained = Vec::new();
    reader.read_to_end(&mut drained).unwrap();
    fill.join().unwrap();
    diagnostic.join().unwrap();
    assert!(
        stopped.is_some(),
        "Second INT did not end the blocked reporting invocation"
    );
    assert_eq!(output.status.code(), Some(130));
    assert!(!home.path().join(".config/inframeld/targets").exists());
}

#[tokio::test]
async fn first_interrupt_during_final_output_preserves_the_already_saved_preference() {
    use std::{
        io::{BufRead, Read},
        process::{Command as ProcessCommand, Stdio},
    };
    let home = TempDir::new().unwrap();
    seed(&home);
    let (mut reader, stdout, fill) = prefilled_pipe();
    let mut child = ProcessCommand::new(assert_cmd::cargo::cargo_bin!("inframeld"))
        .args(["target", "use", "dev", "--json"])
        .env_clear()
        .env("HOME", home.path())
        .env("PATH", "")
        .env("INFRAMELD_TARGET", "prod")
        .stdout(Stdio::from(stdout))
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let stderr = child.stderr.take().unwrap();
    let (sent, arrived) = std::sync::mpsc::channel();
    let diagnostics = std::thread::spawn(move || {
        for line in std::io::BufReader::new(stderr).lines() {
            if line.unwrap().starts_with("warning:") {
                let _ = sent.send(());
            }
        }
    });
    let mut child = RunningCli(Some(child));
    // This warning is emitted by final reporting after the local save completed.
    arrived.recv_timeout(Duration::from_secs(5)).unwrap();
    assert!(child.0.as_mut().unwrap().try_wait().unwrap().is_none());
    assert!(
        ProcessCommand::new("/bin/kill")
            .args(["-INT", &child.0.as_ref().unwrap().id().to_string()])
            .status()
            .unwrap()
            .success()
    );
    let (output, stopped) = child.finish_or_kill(Duration::from_secs(2)).await;
    let mut drained = Vec::new();
    reader.read_to_end(&mut drained).unwrap();
    fill.join().unwrap();
    diagnostics.join().unwrap();
    let saved: Value =
        serde_json::from_slice(&fs::read(home.path().join(".config/inframeld/targets")).unwrap())
            .unwrap();
    assert_eq!(saved["selectedTarget"], "dev");
    assert!(
        stopped,
        "First INT during final output did not end the invocation"
    );
    assert_eq!(output.status.code(), Some(130));
}

#[tokio::test]
async fn a_ca_named_pipe_is_rejected_without_waiting_for_a_writer() {
    use std::process::{Command as ProcessCommand, Stdio};
    let home = TempDir::new().unwrap();
    let certificates = TempDir::new().unwrap();
    let pipe = certificates.path().join("operator.pem");
    assert!(
        ProcessCommand::new("/usr/bin/mkfifo")
            .arg(&pipe)
            .status()
            .unwrap()
            .success()
    );
    let child = ProcessCommand::new(assert_cmd::cargo::cargo_bin!("inframeld"))
        .args([
            "target",
            "add",
            "dev",
            "--url",
            "https://127.0.0.1:9",
            "--ca-cert",
            pipe.to_str().unwrap(),
            "--json",
        ])
        .env_clear()
        .env("HOME", home.path())
        .env("PATH", "")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .unwrap();
    let mut child = RunningCli(Some(child));
    let (output, stopped) = child.finish_or_kill(Duration::from_secs(2)).await;
    assert!(stopped, "Nonregular CA input blocked before validation");
    assert_eq!(result(&output)["error"]["code"], "invalid_ca_file");
    assert_eq!(fs::read_dir(home.path()).unwrap().count(), 0);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn concurrent_registration_and_selection_keep_both_local_effects() {
    let server = discovery_fixture(false, false).await;
    let home = TempDir::new().unwrap();
    let certificates = TempDir::new().unwrap();
    let ca = certificates.path().join("operator.pem");
    fs::write(&ca, &server.pem).unwrap();
    let api = format!("{}/api/v1", server.url);
    let add = |label| {
        invoke(
            &home,
            &[
                "target",
                "add",
                label,
                "--url",
                &api,
                "--ca-cert",
                ca.to_str().unwrap(),
                "--json",
            ],
            None,
        )
    };
    assert!(add("prod").status.success());
    let (registered, selected) = std::thread::scope(|scope| {
        let registered = scope.spawn(|| add("dev"));
        let selected = scope.spawn(|| invoke(&home, &["target", "use", "prod", "--json"], None));
        (registered.join().unwrap(), selected.join().unwrap())
    });
    assert!(registered.status.success() && selected.status.success());
    let state: Value =
        serde_json::from_slice(&fs::read(home.path().join(".config/inframeld/targets")).unwrap())
            .unwrap();
    assert_eq!(state["selectedTarget"], "prod");
    assert_eq!(state["targets"].as_object().unwrap().len(), 2);
    assert_eq!(server.requests.lock().unwrap().len(), 6);
}
