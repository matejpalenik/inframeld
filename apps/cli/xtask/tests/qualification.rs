//! Exercise native artifact gates, safe installation and unchanged user-state evidence.

// Assertions and fixture setup fail immediately on unmet expectations.
#![allow(clippy::unwrap_used)]
use inframeld_cli::metadata::BuildMetadata;
use inframeld_cli_xtask::{archive, verify};
use std::{fs, path::Path};
use tempfile::TempDir;
use xz2::write::XzEncoder;

fn fixture(path: &Path, metadata: &[u8]) {
    fixture_with_binary(path, metadata, b"executable");
}

fn fixture_with_binary(path: &Path, metadata: &[u8], executable: &[u8]) {
    let mut bundle = tar::Builder::new(XzEncoder::new(fs::File::create(path).unwrap(), 6));
    let target = BuildMetadata::embedded().unwrap().target;
    for (name, bytes) in [
        ("inframeld", executable),
        ("LICENSE", b"Apache".as_slice()),
        ("README.md", b"guide".as_slice()),
        ("compatibility.json", metadata),
    ] {
        let mut header = tar::Header::new_gnu();
        header.set_size(bytes.len() as u64);
        header.set_mode(if name == "inframeld" { 0o755 } else { 0o644 });
        header.set_cksum();
        bundle
            .append_data(&mut header, format!("inframeld-cli-{target}/{name}"), bytes)
            .unwrap();
    }
    bundle.into_inner().unwrap().finish().unwrap();
    archive::normalize(path, 123).unwrap();
}

#[test]
fn valid_metadata_is_accepted_and_false_release_claim_is_rejected() {
    let directory = TempDir::new().unwrap();
    let path = directory.path().join("bundle.tar.xz");
    let metadata = BuildMetadata::embedded().unwrap();
    fixture(&path, &serde_json::to_vec(&metadata).unwrap());
    assert_eq!(verify::inspect(&path, &metadata.target).unwrap(), metadata);
    let mut invalid = serde_json::to_value(&metadata).unwrap();
    invalid["status"] = "released".into();
    invalid["qualifiedRuntime"] = "unqualified".into();
    fixture(&path, &serde_json::to_vec(&invalid).unwrap());
    assert!(verify::inspect(&path, &metadata.target).is_err());
}

#[test]
fn corrupted_bytes_and_wrong_targets_are_rejected_before_execution() {
    let directory = TempDir::new().unwrap();
    let path = directory.path().join("bundle.tar.xz");
    let metadata = BuildMetadata::embedded().unwrap();
    fixture(&path, &serde_json::to_vec(&metadata).unwrap());
    assert!(verify::inspect(&path, "wrong-target").is_err());
    fs::write(&path, b"corrupt").unwrap();
    assert!(verify::inspect(&path, &metadata.target).is_err());
}

#[test]
fn installation_preserves_existing_files_and_handles_spaces() {
    let directory = tempfile::Builder::new()
        .prefix("installation with spaces ")
        .tempdir()
        .unwrap();
    let source = directory.path().join("source");
    let destination = directory.path().join("bin/inframeld");
    fs::write(&source, b"new").unwrap();
    verify::install(&source, &destination).unwrap();
    assert_eq!(fs::read(&destination).unwrap(), b"new");
    fs::write(&source, b"replacement").unwrap();
    assert!(verify::install(&source, &destination).is_err());
    assert_eq!(fs::read(&destination).unwrap(), b"new");
    fs::remove_file(destination).unwrap();
    assert_eq!(fs::read(source).unwrap(), b"replacement");
}

#[test]
fn artifact_that_creates_unexpected_user_files_fails_qualification() {
    let directory = TempDir::new().unwrap();
    let path = directory.path().join("bundle.tar.xz");
    let metadata = BuildMetadata::embedded().unwrap();
    let executable = format!(
        "#!/bin/sh\nprintf extra > \"$HOME/unwanted\"\nprintf '%s' '{}'\n",
        metadata.render()
    );
    fixture_with_binary(
        &path,
        &serde_json::to_vec(&metadata).unwrap(),
        executable.as_bytes(),
    );
    assert!(verify::artifact(&path, &metadata.target).is_err());
}

#[test]
fn mismatched_evidence_is_rejected_without_debug_assertions() {
    let first = verify::Evidence {
        archive_sha256: "first".into(),
        binary_sha256: "binary".into(),
        metadata: BuildMetadata::embedded().unwrap(),
        permission_denial_checked: true,
    };
    assert!(verify::compare(&first, &first).is_ok());
    let mut second = first.clone();
    second.archive_sha256 = "different".into();
    assert!(verify::compare(&first, &second).is_err());
}
