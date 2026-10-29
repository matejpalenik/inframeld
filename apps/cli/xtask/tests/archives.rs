//! Verify deterministic normalization and preservation of archives rejected before rewrite.

// Assertions and fixture construction deliberately fail immediately.
#![allow(clippy::unwrap_used)]
use inframeld_cli_xtask::archive;
use sha2::{Digest, Sha256};
use std::{
    fs,
    io::{Cursor, Read},
    path::Path,
};
use tempfile::TempDir;
use xz2::{read::XzDecoder, write::XzEncoder};

fn fixture(path: &Path, identity: u64) {
    let mut builder = tar::Builder::new(XzEncoder::new(fs::File::create(path).unwrap(), 6));
    for (name, body) in [
        ("package/inframeld", b"executable".as_slice()),
        ("package/README.md", b"guide".as_slice()),
    ] {
        let mut header = tar::Header::new_gnu();
        header.set_size(body.len() as u64);
        header.set_mode(if name.ends_with("inframeld") {
            0o755
        } else {
            0o644
        });
        header.set_uid(identity);
        header.set_gid(identity);
        header.set_mtime(identity);
        header.set_cksum();
        builder
            .append_data(&mut header, name, Cursor::new(body))
            .unwrap();
    }
    builder.into_inner().unwrap().finish().unwrap();
}

#[test]
fn normalization_preserves_payload_and_removes_host_metadata() {
    let directory = TempDir::new().unwrap();
    let first = directory.path().join("first.tar.xz");
    let second = directory.path().join("second.tar.xz");
    fixture(&first, 100);
    fixture(&second, 200);
    archive::normalize(&first, 123).unwrap();
    archive::normalize(&second, 123).unwrap();
    assert_eq!(fs::read(&first).unwrap(), fs::read(&second).unwrap());
    let mut bundle = tar::Archive::new(XzDecoder::new(fs::File::open(&first).unwrap()));
    for entry in bundle.entries().unwrap() {
        let mut entry = entry.unwrap();
        assert_eq!(entry.header().uid().unwrap(), 0);
        assert_eq!(entry.header().mtime().unwrap(), 123);
        let mut bytes = Vec::new();
        entry.read_to_end(&mut bytes).unwrap();
        if entry.path().unwrap().ends_with("inframeld") {
            assert_eq!(entry.header().mode().unwrap(), 0o755);
            assert_eq!(bytes, b"executable");
        }
    }
    let digest = format!("{:x}", Sha256::digest(fs::read(&first).unwrap()));
    assert!(
        fs::read_to_string(first.with_extension("xz.sha256"))
            .unwrap()
            .starts_with(&digest)
    );
}

#[test]
fn invalid_epoch_does_not_replace_original() {
    let directory = TempDir::new().unwrap();
    let path = directory.path().join("archive.tar.xz");
    fs::write(&path, b"original").unwrap();
    assert!(archive::normalize(&path, u64::MAX).is_err());
    assert_eq!(fs::read(path).unwrap(), b"original");
}
