//! Read and normalize bounded distribution archives without executing their payloads.
//!
//! Rewrites are staged before replacement. The archive is replaced before its
//! checksum file is written, so a checksum-write failure may leave updated bytes.

use crate::{Error, Result};
use sha2::{Digest, Sha256};
use std::{
    collections::BTreeSet,
    fs,
    io::Read,
    path::{Component, Path, PathBuf},
};
use xz2::{read::XzDecoder, write::XzEncoder};

const MAX_BYTES: u64 = 128 * 1024 * 1024;

/// One validated archive member retained for normalization or inspection.
#[derive(Debug)]
pub(crate) struct Entry {
    pub path: PathBuf,
    pub bytes: Vec<u8>,
    pub mode: u32,
    pub directory: bool,
}

/// Reject unsafe members and excessive expanded data before returning sorted entries.
pub(crate) fn read(path: &Path) -> Result<Vec<Entry>> {
    let mut archive = tar::Archive::new(XzDecoder::new(fs::File::open(path)?));
    let mut entries = Vec::new();
    let mut paths = BTreeSet::new();
    let mut total = 0u64;
    for entry in archive.entries()? {
        let mut entry = entry?;
        let path = entry.path()?.into_owned();
        if !path
            .components()
            .all(|part| matches!(part, Component::Normal(_)))
            || !paths.insert(path.clone())
        {
            return Err(Error::Invalid(
                "archive contains an unsafe or duplicate path".into(),
            ));
        }
        let kind = entry.header().entry_type();
        if !(kind.is_file() || kind.is_dir()) || entries.len() >= 32 {
            return Err(Error::Invalid(
                "archive must contain at most 32 regular files/directories".into(),
            ));
        }
        total = total
            .checked_add(entry.size())
            .ok_or_else(|| Error::Invalid("archive size overflow".into()))?;
        if total > MAX_BYTES {
            return Err(Error::Invalid("archive exceeds 128 MiB".into()));
        }
        let mut bytes = Vec::new();
        entry.read_to_end(&mut bytes)?;
        entries.push(Entry {
            path,
            bytes,
            mode: entry.header().mode()?,
            directory: kind.is_dir(),
        });
    }
    entries.sort_by(|a, b| a.path.cmp(&b.path));
    Ok(entries)
}

/// Hash one bounded distribution artifact.
///
/// # Errors
/// Returns failed I/O or an oversized artifact error.
pub fn digest(path: &Path) -> Result<String> {
    let mut bytes = Vec::new();
    fs::File::open(path)?
        .take(MAX_BYTES + 1)
        .read_to_end(&mut bytes)?;
    if bytes.len() as u64 > MAX_BYTES {
        return Err(Error::Invalid("artifact exceeds 128 MiB".into()));
    }
    Ok(format!("{:x}", Sha256::digest(bytes)))
}

/// Normalize the tar representation and regenerate its checksum.
///
/// # Errors
/// Invalid archives and epochs leave the original archive intact.
pub fn normalize(path: &Path, epoch: u64) -> Result<()> {
    if epoch > u64::from(u32::MAX) {
        return Err(Error::Invalid("epoch exceeds 4294967295".into()));
    }
    rewrite(path, epoch, None)
}

pub(crate) fn stamp(path: &Path, epoch: u64, metadata: &[u8]) -> Result<()> {
    rewrite(path, epoch, Some(metadata))
}

fn rewrite(path: &Path, epoch: u64, metadata: Option<&[u8]>) -> Result<()> {
    if epoch > u64::from(u32::MAX) {
        return Err(Error::Invalid("epoch exceeds 4294967295".into()));
    }
    let mut entries = read(path)?;
    if let Some(bytes) = metadata {
        let entry = entries
            .iter_mut()
            .find(|entry| {
                entry
                    .path
                    .file_name()
                    .is_some_and(|name| name == "compatibility.json")
            })
            .ok_or_else(|| Error::Invalid("missing metadata payload".into()))?;
        entry.bytes = bytes.to_vec();
    }
    let parent = path
        .parent()
        .ok_or_else(|| Error::Invalid("archive needs a parent directory".into()))?;
    let staged = tempfile::NamedTempFile::new_in(parent)?;
    let mut target = tar::Builder::new(XzEncoder::new(staged.reopen()?, 6));
    for entry in entries {
        let mut header = tar::Header::new_gnu();
        header.set_entry_type(if entry.directory {
            tar::EntryType::Directory
        } else {
            tar::EntryType::Regular
        });
        header.set_size(entry.bytes.len() as u64);
        header.set_uid(0);
        header.set_gid(0);
        header.set_mtime(epoch);
        header.set_mode(if entry.directory || entry.mode & 0o111 != 0 {
            0o755
        } else {
            0o644
        });
        header.set_cksum();
        target.append_data(&mut header, entry.path, entry.bytes.as_slice())?;
    }
    target.into_inner()?.finish()?;
    staged.persist(path).map_err(|error| error.error)?;
    let name = path
        .file_name()
        .ok_or_else(|| Error::Invalid("archive needs a filename".into()))?
        .to_string_lossy();
    fs::write(checksum_path(path), format!("{}  {name}\n", digest(path)?))?;
    Ok(())
}

#[must_use]
pub(crate) fn checksum_path(path: &Path) -> PathBuf {
    let mut name = path.as_os_str().to_owned();
    name.push(".sha256");
    PathBuf::from(name)
}
