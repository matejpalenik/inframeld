//! Exercise the offline executable's machine channel without writable user state.

// Behavioral assertions deliberately stop on invalid fixtures or observations.
#![allow(clippy::unwrap_used)]

use std::{
    io::{self, Write},
    os::unix::{ffi::OsStringExt, fs::PermissionsExt},
    process::{Command as ProcessCommand, Output, Stdio},
    time::{Duration, Instant},
};

use assert_cmd::{Command, cargo::cargo_bin_cmd};
use inframeld_cli::{metadata::BuildMetadata, run};
use serde_json::{Value, json};
use tempfile::TempDir;

fn isolated(home: &TempDir) -> Command {
    let mut command = cargo_bin_cmd!("inframeld");
    command
        .env_clear()
        .env("HOME", home.path())
        .env("PATH", "")
        .current_dir(home.path())
        .timeout(Duration::from_secs(5));
    command
}

fn invoke(arguments: &[&str]) -> Output {
    let home = TempDir::new().unwrap();
    std::fs::set_permissions(home.path(), std::fs::Permissions::from_mode(0o500)).unwrap();
    let output = isolated(&home).args(arguments).output().unwrap();
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
    std::fs::set_permissions(home.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
    output
}

fn object(output: &Output) -> Value {
    assert!(output.stdout.len() <= 16_384);
    assert!(output.stderr.len() <= 1_024);
    assert_eq!(output.stdout.last(), Some(&b'\n'));
    serde_json::from_slice(&output.stdout).unwrap()
}

fn usage(arguments: &[&str], mode: &str, jsonl: bool) {
    let output = invoke(arguments);
    assert_eq!(output.status.code(), Some(2));
    let value = object(&output);
    let result = if jsonl {
        assert!(!output.stdout.strip_suffix(b"\n").unwrap().contains(&b'\n'));
        assert_eq!(value["schemaVersion"], 1);
        assert_eq!(value["type"], "result");
        value["result"].clone()
    } else {
        value
    };
    assert_eq!(
        result,
        json!({
            "schemaVersion": 1,
            "mode": mode,
            "outcome": "failed",
            "data": null,
            "error": {
                "source": "cli",
                "code": "invalid_arguments",
                "message": "Check the supplied arguments and use --help for usage."
            },
            "warnings": []
        })
    );
    assert_eq!(
        output.stderr,
        b"error: Check the supplied arguments and use --help for usage.\n"
    );
}

fn assert_version_help(arguments: &[&str]) {
    let output = invoke(arguments);
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    assert!(output.stdout.len() <= 16_384);
    assert!(!output.stdout.contains(&0x1b));
    let text = String::from_utf8(output.stdout).unwrap();
    let missing: Vec<_> = [
        "--json",
        "--jsonl",
        "--dry-run",
        "--no-input",
        "--plain",
        "--no-color",
        "--help",
    ]
    .into_iter()
    .filter(|flag| !text.split_whitespace().any(|token| token == *flag))
    .collect();
    assert!(
        text.contains("Usage: inframeld version") && missing.is_empty(),
        "Version help must show canonical usage and every global option. Missing: {missing:?}\n{text}"
    );
    assert!(!text.contains("--unknown"));
    assert!(!text.starts_with('{'));
}

#[test]
fn version_json_matches_embedded_identity_without_remote_qualification() {
    let metadata = BuildMetadata::embedded().unwrap();
    for arguments in [["version", "--json"], ["--json", "version"]] {
        let output = invoke(&arguments);
        assert!(output.status.success());
        assert!(output.stderr.is_empty());
        let result = object(&output);
        assert_eq!(result["schemaVersion"], 1);
        assert_eq!(result["mode"], "execute");
        assert_eq!(result["outcome"], "succeeded");
        assert_eq!(result["error"], Value::Null);
        assert_eq!(result["warnings"], json!([]));
        assert_eq!(
            result["data"],
            json!({
                "cliVersion": metadata.cli_version,
                "revision": if metadata.revision == "unknown" {
                    None
                } else {
                    Some(metadata.revision.as_str())
                },
                "sourceDirty": metadata.source_dirty,
                "target": metadata.target,
                "qualifiedRuntime": null,
                "policy": "matching-qualified-releases",
                "buildStatus": "development",
                "remoteVerification": "unavailable",
                "remoteCompatibility": "unverified"
            })
        );
    }
    let human = invoke(&["version"]);
    assert!(human.status.success());
    assert_eq!(human.stdout, metadata.render().as_bytes());
}

#[test]
fn explicit_jsonl_has_only_one_final_version_result() {
    let output = invoke(&["version", "--jsonl"]);
    assert!(output.status.success());
    assert!(output.stderr.is_empty());
    assert!(!output.stdout.strip_suffix(b"\n").unwrap().contains(&b'\n'));
    let wrapper = object(&output);
    assert_eq!(wrapper["schemaVersion"], 1);
    assert_eq!(wrapper["type"], "result");
    assert_eq!(wrapper["result"]["mode"], "execute");
    assert_eq!(wrapper["result"]["outcome"], "succeeded");
    assert_eq!(
        wrapper["result"]["data"]["remoteCompatibility"],
        "unverified"
    );
}

#[test]
fn dry_run_describes_the_offline_read_without_claiming_metadata_observations() {
    for format in ["--json", "--jsonl"] {
        let output = invoke(&["version", "--dry-run", format, "--no-input"]);
        assert!(output.status.success());
        assert!(output.stderr.is_empty());
        let value = object(&output);
        let result = if format == "--jsonl" {
            &value["result"]
        } else {
            &value
        };
        assert_eq!(result["mode"], "dryRun");
        assert_eq!(result["outcome"], "succeeded");
        assert_eq!(result["error"], Value::Null);
        assert_eq!(result["warnings"], json!([]));
        assert_eq!(
            result["data"],
            json!({
                "command": "version",
                "intendedReads": ["embeddedBuildMetadata"],
                "intendedDestination": "stdout",
                "outgoingDataCategories": ["buildIdentity", "compatibilityPolicy"],
                "intendedEffects": ["writeVersionInformationToStdout"],
                "checksPerformed": ["argumentsValidated"],
                "unresolvedChoices": [],
                "operationPerformed": false
            })
        );
    }
    let human = invoke(&["version", "--dry-run", "--plain"]);
    assert!(human.status.success());
    let text = String::from_utf8(human.stdout).unwrap();
    assert!(text.contains("Embedded values were not read"));
    assert!(text.contains("Remote compatibility was not checked"));
    assert!(!text.contains("Revision:"));
}

#[test]
fn missing_command_and_output_conflicts_return_the_requested_failure_channel() {
    for arguments in [
        vec!["--json"],
        vec!["version", "--version", "--json"],
        vec!["--json", "--jsonl", "--version"],
    ] {
        usage(&arguments, "execute", false);
    }
    usage(&["--jsonl"], "execute", true);
    usage(&["--json", "--dry-run"], "dryRun", false);
    usage(&["--jsonl", "--dry-run"], "dryRun", true);
    usage(&["--json", "--jsonl", "--dry-run"], "dryRun", false);
    let human = invoke(&["--dry-run"]);
    assert_eq!(human.status.code(), Some(2));
    assert!(human.stdout.is_empty());
}

#[test]
fn diagnostic_intent_stops_at_the_delimiter_and_ignores_embedded_values() {
    usage(&["--json", "--", "--help"], "execute", false);
    usage(&["--json", "version", "--", "--dry-run"], "execute", false);
    usage(
        &["--json", "--name=--dry-run", "--unknown"],
        "execute",
        false,
    );
    usage(&["--jsonl", "--dry-run", "--unknown"], "dryRun", true);
    let output = invoke(&["version", "--", "--json"]);
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
}

#[test]
fn exact_help_wins_but_output_conflicts_do_not_become_short_version_success() {
    for arguments in [
        vec!["--json", "--jsonl", "--help", "--unknown"],
        vec!["version", "--help", "--unknown", "--json"],
        vec!["--json", "--jsonl", "-h"],
    ] {
        let output = invoke(&arguments);
        assert!(output.status.success());
        assert!(output.stderr.is_empty());
        let text = String::from_utf8(output.stdout).unwrap();
        assert!(text.contains("Usage:"));
        assert!(!text.contains("--unknown"));
        assert!(!text.starts_with('{'));
    }
    let short = invoke(&["--json", "--version"]);
    assert!(short.status.success());
    assert_eq!(short.stdout, b"inframeld 0.0.0\n");
    usage(&["--json", "--jsonl", "--version"], "execute", false);
}

#[test]
fn version_help_lists_global_options_with_canonical_usage() {
    assert_version_help(&["version", "--help"]);
    assert_version_help(&["version", "-h"]);
}

#[test]
fn version_help_stays_complete_when_exact_help_overrides_invalid_flags() {
    for arguments in [
        vec!["version", "--help", "--json", "--jsonl", "--unknown"],
        vec!["--json", "version", "--unknown", "-h", "--jsonl"],
    ] {
        assert_version_help(&arguments);
    }
}

#[test]
fn unsafe_arguments_are_not_echoed_to_either_human_or_machine_diagnostics() {
    let hostile = format!("--private-\u{1b}[31m\r\n{}", "sensitive".repeat(2_000));
    for arguments in [vec![hostile.as_str()], vec!["--json", hostile.as_str()]] {
        let output = invoke(&arguments);
        assert_eq!(output.status.code(), Some(2));
        assert!(output.stdout.len() <= 16_384);
        assert!(output.stderr.len() <= 1_024);
        for bytes in [&output.stdout, &output.stderr] {
            assert!(!bytes.contains(&0x1b));
            assert!(!String::from_utf8_lossy(bytes).contains("sensitive"));
            assert!(!bytes.contains(&b'\r'));
        }
    }
}

#[test]
fn terminal_controls_do_not_style_or_change_the_machine_payload() {
    let home = TempDir::new().unwrap();
    for (name, value) in [("NO_COLOR", "1"), ("TERM", "dumb")] {
        let output = isolated(&home)
            .env(name, value)
            .args(["version", "--json", "--plain", "--no-color", "--no-input"])
            .output()
            .unwrap();
        assert!(output.status.success());
        assert!(output.stderr.is_empty());
        assert!(!output.stdout.contains(&0x1b));
        assert_eq!(object(&output)["outcome"], "succeeded");
    }
}

#[test]
fn harmless_root_flags_keep_help_and_short_version_stays_plain() {
    for arguments in [
        vec!["--no-input", "--plain", "--no-color"],
        vec!["--unknown", "version", "--help"],
    ] {
        let output = invoke(&arguments);
        assert!(output.status.success());
        assert!(output.stderr.is_empty());
        assert!(output.stdout.len() <= 16_384);
        let text = String::from_utf8(output.stdout).unwrap();
        assert!(text.contains("Usage: inframeld [OPTIONS]"));
        assert!(!text.contains("--unknown"));
    }
    let short = invoke(&["-V", "--jsonl"]);
    assert!(short.status.success());
    assert_eq!(short.stdout, b"inframeld 0.0.0\n");
    usage(&["--json", "--jsonl", "-V"], "execute", false);
    usage(&["--json", "--", "--jsonl", "--dry-run"], "execute", false);
}

#[test]
fn non_utf8_arguments_cannot_corrupt_the_utf8_machine_failure() {
    let home = TempDir::new().unwrap();
    let argument = std::ffi::OsString::from_vec(b"--private-\xff".to_vec());
    let output = isolated(&home)
        .arg("--json")
        .arg(argument)
        .output()
        .unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert_eq!(object(&output)["error"]["code"], "invalid_arguments");
    assert!(!String::from_utf8_lossy(&output.stderr).contains("private"));
}

#[test]
fn builtin_help_uses_static_command_text_without_reflecting_the_process_label() {
    let mut output = Vec::new();
    let mut diagnostic = Vec::new();
    let code = run(
        ["private-\u{1b}[31m-label", "help", "version"],
        &mut output,
        &mut diagnostic,
    )
    .unwrap();
    assert_eq!(code, 0);
    assert!(diagnostic.is_empty());
    assert!(!output.contains(&0x1b));
    let text = String::from_utf8(output).unwrap();
    assert!(!text.contains("private"));
    assert!(text.contains("Usage: inframeld version"));
}

#[derive(Debug, Default)]
struct OutputFault {
    bytes: Vec<u8>,
    fail_after: Option<usize>,
    fail_flush: bool,
    short: bool,
    zero_write: bool,
}

impl Write for OutputFault {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if self.zero_write {
            return Ok(0);
        }
        if self
            .fail_after
            .is_some_and(|limit| self.bytes.len() >= limit)
        {
            return Err(io::ErrorKind::BrokenPipe.into());
        }
        let available = self
            .fail_after
            .map_or(bytes.len(), |limit| limit - self.bytes.len());
        let count = bytes
            .len()
            .min(available)
            .min(if self.short { 3 } else { usize::MAX });
        self.bytes.extend_from_slice(&bytes[..count]);
        Ok(count)
    }

    fn flush(&mut self) -> io::Result<()> {
        if self.fail_flush {
            Err(io::ErrorKind::BrokenPipe.into())
        } else {
            Ok(())
        }
    }
}

#[test]
fn machine_write_or_flush_failure_is_nonzero_without_a_replacement_result() {
    for mut output in [
        OutputFault {
            fail_after: Some(0),
            ..OutputFault::default()
        },
        OutputFault {
            fail_after: Some(30),
            ..OutputFault::default()
        },
        OutputFault {
            fail_flush: true,
            ..OutputFault::default()
        },
        OutputFault {
            zero_write: true,
            ..OutputFault::default()
        },
    ] {
        let mut diagnostic = Vec::new();
        let code = run(
            ["inframeld", "version", "--json"],
            &mut output,
            &mut diagnostic,
        )
        .unwrap();
        assert_eq!(code, 1);
        assert!(output.bytes.len() <= 16_384);
        assert_eq!(diagnostic, b"error: CLI output could not be written.\n");
    }
}

#[test]
fn broken_human_diagnostic_does_not_suppress_the_final_machine_usage_result() {
    let mut output = Vec::new();
    let mut diagnostic = OutputFault {
        fail_after: Some(0),
        ..OutputFault::default()
    };
    let code = run(
        ["inframeld", "--jsonl", "--dry-run", "--unknown"],
        &mut output,
        &mut diagnostic,
    )
    .unwrap();
    assert_eq!(code, 2);
    assert!(diagnostic.bytes.is_empty());
    let value: Value = serde_json::from_slice(&output).unwrap();
    assert_eq!(value["type"], "result");
    assert_eq!(value["result"]["mode"], "dryRun");
    assert_eq!(value["result"]["error"]["code"], "invalid_arguments");
}

#[test]
fn human_usage_keeps_its_exit_when_the_diagnostic_write_or_flush_fails() {
    let codes = [
        OutputFault {
            fail_after: Some(0),
            ..OutputFault::default()
        },
        OutputFault {
            fail_flush: true,
            ..OutputFault::default()
        },
        OutputFault {
            zero_write: true,
            ..OutputFault::default()
        },
    ]
    .map(|mut diagnostic| {
        let mut output = Vec::new();
        let code = run(["inframeld", "--unknown"], &mut output, &mut diagnostic)
            .map_err(|error| error.kind());
        assert!(output.is_empty());
        assert!(diagnostic.bytes.len() <= 1_024);
        code
    });
    assert_eq!(codes, [Ok(2), Ok(2), Ok(2)]);
}

#[test]
fn successive_short_writes_complete_one_result_before_success() {
    let mut output = OutputFault {
        short: true,
        ..OutputFault::default()
    };
    let mut diagnostic = Vec::new();
    assert_eq!(
        run(
            ["inframeld", "version", "--json"],
            &mut output,
            &mut diagnostic
        )
        .unwrap(),
        0
    );
    assert!(diagnostic.is_empty());
    assert_eq!(
        serde_json::from_slice::<Value>(&output.bytes).unwrap()["outcome"],
        "succeeded"
    );
}

#[test]
// A deadline failure panics only after this test's child has been killed and reaped.
#[allow(clippy::panic)]
fn real_broken_machine_pipe_fails_while_plain_version_keeps_its_pipe_exception() {
    for (arguments, status) in [
        (vec!["version", "--json"], 1),
        (vec!["version", "--jsonl"], 1),
        (vec!["version"], 0),
        (vec!["--help"], 0),
        (vec!["--version"], 0),
    ] {
        let home = TempDir::new().unwrap();
        let (reader, writer) = io::pipe().unwrap();
        drop(reader);
        let mut process = ProcessCommand::new(assert_cmd::cargo::cargo_bin!("inframeld"));
        process
            .args(arguments)
            .env_clear()
            .env("HOME", home.path())
            .env("PATH", "");
        process.current_dir(home.path()).stdout(Stdio::from(writer));
        // assert_cmd's capture replaces a configured stdout, so retain this pipe
        // on the actual owned child and reap it before inspecting the result.
        let mut child = process.stderr(Stdio::piped()).spawn().unwrap();
        let deadline = Instant::now() + Duration::from_secs(5);
        loop {
            if child.try_wait().unwrap().is_some() {
                break;
            }
            if Instant::now() >= deadline {
                child.kill().unwrap();
                child.wait().unwrap();
                panic!("offline command exceeded its process deadline");
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        let output = child.wait_with_output().unwrap();
        assert_eq!(output.status.code(), Some(status));
        assert!(output.stdout.is_empty());
        assert!(output.stderr.len() <= 1_024);
        assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
    }
}

#[test]
// A deadline failure panics only after this test's child has been killed and reaped.
#[allow(clippy::panic)]
fn a_closed_stderr_diagnostic_cannot_make_an_invalid_invocation_succeed() {
    let home = TempDir::new().unwrap();
    std::fs::set_permissions(home.path(), std::fs::Permissions::from_mode(0o500)).unwrap();
    let (reader, writer) = io::pipe().unwrap();
    // Closing the reader before spawn makes failure independent of scheduling.
    drop(reader);
    let mut child = ProcessCommand::new(assert_cmd::cargo::cargo_bin!("inframeld"))
        .arg("--unknown")
        .env_clear()
        .env("HOME", home.path())
        .env("PATH", "")
        .current_dir(home.path())
        .stdout(Stdio::piped())
        .stderr(Stdio::from(writer))
        .spawn()
        .unwrap();
    let deadline = Instant::now() + Duration::from_secs(5);
    loop {
        if child.try_wait().unwrap().is_some() {
            break;
        }
        if Instant::now() >= deadline {
            child.kill().unwrap();
            child.wait().unwrap();
            panic!("offline command exceeded its process deadline");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    let output = child.wait_with_output().unwrap();
    std::fs::set_permissions(home.path(), std::fs::Permissions::from_mode(0o700)).unwrap();
    assert_eq!(output.status.code(), Some(2));
    assert!(output.stdout.is_empty());
    assert!(output.stderr.is_empty());
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
}
