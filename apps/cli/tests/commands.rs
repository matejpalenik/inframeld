//! Check offline arguments, streams, exit codes and absence of user-state changes.

// Test assertions deliberately panic on unmet behavioral expectations.
#![allow(clippy::unwrap_used)]
use assert_cmd::{Command, cargo::cargo_bin_cmd};
use predicates::prelude::*;
use std::os::unix::fs::PermissionsExt;
use tempfile::TempDir;

fn isolated(home: &TempDir) -> Command {
    let mut command = cargo_bin_cmd!("inframeld");
    command.env_clear().env("HOME", home.path()).env("PATH", "");
    command.current_dir(home.path());
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
