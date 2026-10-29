//! Keep missing packaging prerequisites actionable without creating user files.

// Process assertions deliberately fail immediately.
#![allow(clippy::unwrap_used)]
use assert_cmd::cargo::cargo_bin_cmd;
use predicates::prelude::*;

#[test]
fn missing_packaging_tool_is_actionable_without_writes() {
    let home = tempfile::tempdir().unwrap();
    cargo_bin_cmd!("inframeld-cli-xtask")
        .env_clear()
        .env("PATH", "")
        .env("HOME", home.path())
        .current_dir(home.path())
        .args(["package", "--target", "aarch64-apple-darwin"])
        .assert()
        .failure()
        .stderr(predicate::str::contains(
            "cargo install --locked --version 0.33.0 cargo-dist",
        ));
    assert_eq!(std::fs::read_dir(home.path()).unwrap().count(), 0);
}
