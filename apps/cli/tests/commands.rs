//! Check offline arguments, streams, exit codes and absence of user-state changes.

// Test assertions deliberately panic on unmet behavioral expectations.
#![allow(clippy::unwrap_used)]
use assert_cmd::{Command, cargo::cargo_bin_cmd};
use predicates::prelude::*;
use std::{os::unix::fs::PermissionsExt, time::Duration};
use tempfile::TempDir;

fn isolated(home: &TempDir) -> Command {
    let mut command = cargo_bin_cmd!("inframeld");
    command.env_clear().env("HOME", home.path()).env("PATH", "");
    command.current_dir(home.path());
    command.timeout(Duration::from_secs(30));
    command
}

#[test]
fn help_is_useful_without_services_or_configuration() {
    let home = TempDir::new().unwrap();
    std::fs::set_permissions(home.path(), std::fs::Permissions::from_mode(0o500)).unwrap();
    for args in [vec![], vec!["--help"], vec!["help"]] {
        isolated(&home).args(args).assert().success().stdout(
            predicate::str::contains("Examples:")
                .and(predicate::str::contains("inframeld version"))
                .and(predicate::str::contains("does not start")),
        );
    }
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
    std::fs::set_permissions(home.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
}

#[test]
fn development_version_never_claims_runtime_qualification() {
    let home = TempDir::new().unwrap();
    isolated(&home).arg("version").assert().success().stdout(
        predicate::str::contains("Development build")
            .and(predicate::str::contains("Qualified runtime: none"))
            .and(predicate::str::contains("Remote compatibility: unverified"))
            .and(predicate::str::contains("Target:"))
            .and(predicate::str::contains("Revision:")),
    );
    isolated(&home)
        .arg("--version")
        .assert()
        .success()
        .stdout(predicate::str::contains("inframeld 0.0.0"));
    isolated(&home)
        .args(["version", "--help"])
        .assert()
        .success();
}

#[test]
fn invalid_invocations_fail_without_effects() {
    let home = TempDir::new().unwrap();
    for args in [["login", "--unknown"], ["version", "--unknown"]] {
        isolated(&home)
            .args(args)
            .assert()
            .code(2)
            .stdout("")
            .stderr(predicate::str::contains("error:"));
    }
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
}

fn bootstrap_files(home: &TempDir) -> [std::path::PathBuf; 3] {
    let host = home.path().join("host.json");
    let request = home.path().join("request.json");
    let execution = home.path().join("execution.json");
    std::fs::write(&host, r#"{"schemaVersion":1,"api":"https://installation.invalid/api","issuer":"https://identity.invalid/","clientId":"inframeld-cli","installationId":"00000000-0000-0000-0000-000000000001","expectedIdentityId":"00000000-0000-0000-0000-000000000002"}"#).unwrap();
    std::fs::write(&request, r#"{"schemaVersion":1,"mode":"bootstrap-first-administrator","expectedInstallationId":"00000000-0000-0000-0000-000000000001","operationId":"original-bootstrap","operatorLabel":"Operator","reason":"Reviewed admission","expectedAccessRevision":0,"expectedIdentityId":"00000000-0000-0000-0000-000000000002"}"#).unwrap();
    std::fs::write(
        &execution,
        r#"{"program":"/this-host-command-must-not-run","args":[],"environment":{}}"#,
    )
    .unwrap();
    [host, request, execution]
}

#[test]
fn bootstrap_dry_run_explains_reviewed_inputs_without_discovery_or_claim() {
    let home = TempDir::new().unwrap();
    let [host, request, execution] = bootstrap_files(&home);
    let output = isolated(&home)
        .args([
            "auth",
            "bootstrap-first-administrator",
            "--host-context",
            host.to_str().unwrap(),
            "--request",
            request.to_str().unwrap(),
            "--exec-spec",
            execution.to_str().unwrap(),
            "--dry-run",
            "--json",
            "--no-input",
        ])
        .output()
        .unwrap();
    assert!(
        output.status.success(),
        "valid bootstrap dry run must explain reviewed input"
    );
    let result: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result.as_object().unwrap().len(), 6);
    assert_eq!(result["mode"], "dryRun");
    assert_eq!(result["outcome"], "succeeded");
    assert_eq!(result["data"]["operation"], "bootstrap-first-administrator");
    assert_eq!(result["data"]["backendVerification"], "not-performed");
    assert_eq!(result["data"]["credentialPersistence"], "none");
    assert!(output.stderr.is_empty());
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 3);
}

#[test]
fn bootstrap_machine_and_plain_dry_runs_share_facts_under_all_global_modes() {
    for flags in [
        vec!["--json"],
        vec!["--jsonl"],
        vec!["--plain", "--no-color"],
    ] {
        let home = TempDir::new().unwrap();
        let [host, request, execution] = bootstrap_files(&home);
        let output = isolated(&home)
            .args(&flags)
            .args([
                "auth",
                "bootstrap-first-administrator",
                "--dry-run",
                "--no-input",
                "--host-context",
                host.to_str().unwrap(),
                "--request",
                request.to_str().unwrap(),
                "--exec-spec",
                execution.to_str().unwrap(),
            ])
            .output()
            .unwrap();
        assert!(output.status.success());
        assert!(output.stderr.is_empty());
        assert!(!output.stdout.contains(&0x1b));
        if flags.contains(&"--plain") {
            let text = String::from_utf8(output.stdout).unwrap();
            assert!(text.contains("Backend eligibility and current admission are unverified"));
            assert!(text.contains("No browser, credential or host command was dispatched"));
        } else {
            let record: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
            let result = if flags.contains(&"--jsonl") {
                assert_eq!(output.stdout.last(), Some(&b'\n'));
                assert!(!output.stdout.strip_suffix(b"\n").unwrap().contains(&b'\n'));
                assert_eq!(record["type"], "result");
                &record["result"]
            } else {
                &record
            };
            assert_eq!(result.as_object().unwrap().len(), 6);
            assert_eq!(result["data"]["providedAccessRevision"], 0);
            assert_eq!(result["data"]["backendVerification"], "not-performed");
            assert_eq!(result["error"], serde_json::Value::Null);
            assert_eq!(result["warnings"], serde_json::json!([]));
        }
        assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 3);
    }
}

#[test]
fn bootstrap_rejects_conflicting_target_before_reading_files_and_missing_input_without_prompt() {
    let home = TempDir::new().unwrap();
    let output = isolated(&home)
        .args([
            "auth",
            "bootstrap-first-administrator",
            "--json",
            "--no-input",
            "--target",
            "protected-target",
            "--host-context",
            "absent",
            "--request",
            "absent",
            "--exec-spec",
            "absent",
        ])
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    let result: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
    assert_eq!(result["error"]["code"], "conflicting_target");
    assert!(!String::from_utf8_lossy(&output.stderr).contains("protected-target"));
    for flags in [vec!["--json"], vec!["--jsonl"], vec![]] {
        isolated(&home)
            .args(["auth", "bootstrap-first-administrator", "--no-input"])
            .args(flags)
            .assert()
            .code(2);
    }
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn bootstrap_rejects_incompatible_oversized_and_symlinked_files_without_echo_or_claim() {
    for kind in ["proof", "binding", "execution", "oversized", "symlink"] {
        let home = TempDir::new().unwrap();
        let [host, request, execution] = bootstrap_files(&home);
        match kind {
            "proof" => std::fs::write(
                &request,
                b"{\"identityProof\":\"protected-secret-sentinel\"}",
            )
            .unwrap(),
            "binding" => {
                let mut value: serde_json::Value =
                    serde_json::from_slice(&std::fs::read(&request).unwrap()).unwrap();
                value["expectedIdentityId"] =
                    serde_json::json!("00000000-0000-0000-0000-000000000099");
                std::fs::write(&request, serde_json::to_vec(&value).unwrap()).unwrap();
            }
            "execution" => std::fs::write(
                &execution,
                b"{\"program\":\"relative-protected-secret-sentinel\"}",
            )
            .unwrap(),
            "oversized" => std::fs::write(&host, vec![b'x'; 65_537]).unwrap(),
            _ => {
                std::fs::remove_file(&request).unwrap();
                std::os::unix::fs::symlink(&host, &request).unwrap();
            }
        }
        let output = isolated(&home)
            .args([
                "--json",
                "--no-input",
                "auth",
                "bootstrap-first-administrator",
                "--dry-run",
                "--host-context",
                host.to_str().unwrap(),
                "--request",
                request.to_str().unwrap(),
                "--exec-spec",
                execution.to_str().unwrap(),
            ])
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(2), "{kind}");
        let result: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(result["error"]["code"], "invalid_bootstrap_input");
        assert!(!String::from_utf8_lossy(&output.stdout).contains("protected-secret-sentinel"));
        assert!(!String::from_utf8_lossy(&output.stderr).contains("protected-secret-sentinel"));
    }
}

#[test]
fn bootstrap_help_exposes_the_leaf_contract_and_private_child_is_intercepted_before_parse() {
    let home = TempDir::new().unwrap();
    let output = isolated(&home)
        .args(["auth", "bootstrap-first-administrator", "--help"])
        .output()
        .unwrap();
    assert!(output.status.success());
    let text = String::from_utf8(output.stdout).unwrap();
    for flag in [
        "--host-context",
        "--request",
        "--exec-spec",
        "--dry-run",
        "--no-input",
        "--json",
        "--jsonl",
    ] {
        assert!(text.contains(flag), "{flag}");
    }
    let output = isolated(&home)
        .arg("--internal-system-browser-launch")
        .write_stdin("{}")
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(1));
    assert_eq!(output.stdout, b"READY1\n");
    assert!(output.stderr.is_empty());
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
}

#[test]
fn bootstrap_human_plan_escapes_control_characters_in_original_operation_id() {
    let home = TempDir::new().unwrap();
    let [host, request, execution] = bootstrap_files(&home);
    let mut value: serde_json::Value =
        serde_json::from_slice(&std::fs::read(&request).unwrap()).unwrap();
    value["operationId"] = serde_json::json!("original\n\u{001b}]52;protected-control");
    std::fs::write(&request, serde_json::to_vec(&value).unwrap()).unwrap();
    let output = isolated(&home)
        .args([
            "auth",
            "bootstrap-first-administrator",
            "--dry-run",
            "--plain",
            "--host-context",
            host.to_str().unwrap(),
            "--request",
            request.to_str().unwrap(),
            "--exec-spec",
            execution.to_str().unwrap(),
        ])
        .output()
        .unwrap();
    assert!(output.status.success());
    assert!(
        !output.stdout.contains(&0x1b),
        "reviewed operation text cannot become terminal control"
    );
    assert!(
        String::from_utf8(output.stdout)
            .unwrap()
            .contains("\\n\\u{1b}")
    );
}

#[test]
fn bootstrap_dry_run_distinguishes_safe_api_issuer_proxy_and_unverified_host_execution() {
    for flags in [vec!["--json"], vec!["--plain"]] {
        let home = TempDir::new().unwrap();
        let [host, request, execution] = bootstrap_files(&home);
        let mut value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&host).unwrap()).unwrap();
        value["api"] = serde_json::json!("https://api.installation.test/v1");
        value["issuer"] = serde_json::json!("https://login.identity.test/issuer/");
        value["proxy"] = serde_json::json!("http://proxy.operator.test:8080");
        std::fs::write(&host, serde_json::to_vec(&value).unwrap()).unwrap();
        let output = isolated(&home)
            .args([
                "auth",
                "bootstrap-first-administrator",
                "--dry-run",
                "--no-input",
                "--host-context",
                host.to_str().unwrap(),
                "--request",
                request.to_str().unwrap(),
                "--exec-spec",
                execution.to_str().unwrap(),
            ])
            .args(&flags)
            .output()
            .unwrap();
        assert!(output.status.success());
        let text = String::from_utf8(output.stdout).unwrap();
        if flags.contains(&"--json") {
            let result: serde_json::Value = serde_json::from_str(&text).unwrap();
            let destinations = &result["data"]["destinations"];
            assert_eq!(destinations["api"], "https://api.installation.test/v1");
            assert_eq!(
                destinations["issuer"],
                "https://login.identity.test/issuer/"
            );
            assert_eq!(destinations["proxy"], "http://proxy.operator.test:8080");
            assert_eq!(
                destinations["hostExecution"],
                "operator-controlled-unverified"
            );
            assert!(
                result["data"]["outgoingDataCategories"]
                    .as_array()
                    .is_some_and(|a| a.len() == 4)
            );
        } else {
            for fact in [
                "https://api.installation.test/v1",
                "https://login.identity.test/issuer/",
                "http://proxy.operator.test:8080",
                "operator-controlled-unverified",
                "transient credentials",
            ] {
                assert!(text.contains(fact), "{fact}");
            }
        }
        assert!(!text.contains("this-host-command-must-not-run"));
    }
}

#[test]
fn bootstrap_dry_run_rejects_malformed_provided_endpoint_and_proxy_without_echo() {
    for (field, value) in [
        ("api", "http://api.installation.test"),
        ("api", "https://user:protected-url-secret@api.test/"),
        ("api", "https://api.test/?protected-url-secret"),
        ("issuer", "https://id.test/#protected-url-secret"),
        ("issuer", "https://id.test/%zz"),
        ("issuer", "https://id.test/../private"),
        ("proxy", "http://user:protected-url-secret@proxy.test:8080"),
    ] {
        let home = TempDir::new().unwrap();
        let [host, request, execution] = bootstrap_files(&home);
        let mut context: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&host).unwrap()).unwrap();
        context[field] = serde_json::json!(value);
        std::fs::write(&host, serde_json::to_vec(&context).unwrap()).unwrap();
        let output = isolated(&home)
            .args([
                "auth",
                "bootstrap-first-administrator",
                "--dry-run",
                "--json",
                "--host-context",
                host.to_str().unwrap(),
                "--request",
                request.to_str().unwrap(),
                "--exec-spec",
                execution.to_str().unwrap(),
            ])
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(2), "{field}");
        let result: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
        assert_eq!(result["error"]["code"], "invalid_bootstrap_input");
        assert!(!String::from_utf8_lossy(&output.stdout).contains("protected-url-secret"));
        assert!(!String::from_utf8_lossy(&output.stderr).contains("protected-url-secret"));
    }
}

#[test]
fn bootstrap_public_noninteractive_execution_rejects_before_any_input_or_network_effect() {
    for flags in [
        vec![],
        vec!["--no-input"],
        vec!["--json"],
        vec!["--jsonl", "--no-input"],
    ] {
        let home = TempDir::new().unwrap();
        let output = isolated(&home)
            .args([
                "auth",
                "bootstrap-first-administrator",
                "--host-context",
                "missing-host",
                "--request",
                "missing-request",
                "--exec-spec",
                "missing-execution",
            ])
            .args(&flags)
            .output()
            .unwrap();
        assert_eq!(output.status.code(), Some(2));
        assert!(String::from_utf8_lossy(&output.stderr).contains("interactive input"));
        if flags.contains(&"--json") || flags.contains(&"--jsonl") {
            let value: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
            let result = if flags.contains(&"--jsonl") {
                &value["result"]
            } else {
                &value
            };
            assert_eq!(result["error"]["code"], "interaction_required");
        }
        assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
    }
}
