//! Reject invalid archive payloads and build identities before native execution.

use std::{collections::BTreeMap, fs, path::Path};

use inframeld_cli::metadata::BuildMetadata;

use crate::{Error, Result, archive};

use super::require;

/// Inspect an artifact before any bundled executable can run.
///
/// # Errors
/// Rejects invalid checksums, paths, metadata and missing required payloads.
pub fn inspect(path: &Path, target: &str) -> Result<BuildMetadata> {
    let checksum = fs::read_to_string(archive::checksum_path(path))?;
    let fields: Vec<_> = checksum.split_whitespace().collect();
    require(
        fields.len() == 2
            && fields[0] == archive::digest(path)?
            && Some(fields[1]) == path.file_name().and_then(|name| name.to_str()),
        "archive checksum mismatch",
    )?;
    let prefix = format!("inframeld-cli-{target}");
    let mut files = BTreeMap::new();
    for entry in archive::read(path)? {
        if entry.directory {
            require(
                entry.path == Path::new(&prefix),
                "unexpected archive directory",
            )?;
            continue;
        }
        let relative = entry
            .path
            .strip_prefix(&prefix)
            .map_err(|_| Error::Invalid("archive target mismatch".into()))?;
        require(
            relative.components().count() == 1,
            "unexpected nested archive payload",
        )?;
        if relative == Path::new("inframeld") {
            require(entry.mode & 0o111 != 0, "binary is not executable")?;
        }
        files.insert(relative.to_owned(), entry.bytes);
    }
    for name in ["inframeld", "LICENSE", "README.md", "compatibility.json"] {
        require(
            files
                .get(Path::new(name))
                .is_some_and(|bytes| !bytes.is_empty()),
            "required archive payload is absent or empty",
        )?;
    }
    require(files.len() == 4, "unexpected extra archive payload")?;
    let metadata =
        BuildMetadata::parse(&files[Path::new("compatibility.json")]).map_err(Error::Invalid)?;
    require(
        metadata.target == target && metadata.cli_version == env!("CARGO_PKG_VERSION"),
        "archive build identity mismatch",
    )?;
    Ok(metadata)
}
