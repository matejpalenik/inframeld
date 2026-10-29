//! Qualify installation and offline execution in an isolated temporary home.

use std::{
    collections::BTreeMap, fs, io::Write, os::unix::fs::PermissionsExt, path::Path,
    process::Command, time::Duration,
};

use inframeld_cli::metadata::BuildMetadata;

use crate::{Error, Result, archive, process};

use super::{Evidence, inspect::inspect, require};

/// Copy into an explicitly selected test destination without replacement.
///
/// Parent directories may be created before a later failure. The staged copy is
/// published without replacing an existing executable.
///
/// # Errors
/// Returns permission, destination conflict or I/O failures without overwriting a file.
pub fn install(source: &Path, destination: &Path) -> Result<()> {
    let parent = destination
        .parent()
        .ok_or_else(|| Error::Invalid("destination needs parent directory".into()))?;
    fs::create_dir_all(parent)?;
    let mut staged = tempfile::NamedTempFile::new_in(parent)?;
    staged.write_all(&fs::read(source)?)?;
    staged
        .as_file()
        .set_permissions(fs::Permissions::from_mode(0o755))?;
    staged
        .persist_noclobber(destination)
        .map_err(|error| error.error)?;
    Ok(())
}

/// Observe all ordinary files so installation and execution cannot hide user-state changes.
fn snapshot(
    root: &Path,
    directory: &Path,
    files: &mut BTreeMap<std::path::PathBuf, Vec<u8>>,
) -> Result<()> {
    for entry in fs::read_dir(directory)? {
        let entry = entry?;
        let kind = entry.file_type()?;
        if kind.is_dir() {
            snapshot(root, &entry.path(), files)?;
        } else if kind.is_file() {
            let relative = entry
                .path()
                .strip_prefix(root)
                .map_err(|_| Error::Invalid("snapshot escaped test home".into()))?
                .to_owned();
            files.insert(relative, fs::read(entry.path())?);
        } else {
            return Err(Error::Invalid("unexpected user-state file type".into()));
        }
    }
    Ok(())
}

/// Run an offline invocation with cleared environment and a disposable home.
fn execute(binary: &Path, home: &Path, args: &[&str]) -> Result<String> {
    let output = process::capture(
        Command::new(binary)
            .args(args)
            .current_dir(home)
            .env_clear()
            .env("HOME", home)
            .env("PATH", ""),
        Duration::from_secs(10),
    )?;
    require(
        output.status.success() && output.stderr.is_empty(),
        "packaged invocation failed",
    )?;
    String::from_utf8(output.stdout)
        .map_err(|_| Error::Invalid("packaged output is not UTF-8".into()))
}

/// Qualify a native archive in an isolated home and installation directory.
///
/// Executes the bundled binary only after inspection. The caller must already
/// trust the artifact's provenance. Checksums do not establish publisher identity.
///
/// # Errors
/// Every failed gate is an explicit error in debug and optimized builds.
pub fn artifact(path: &Path, target: &str) -> Result<Evidence> {
    let metadata = inspect(path, target)?;
    let native = BuildMetadata::embedded().map_err(Error::Invalid)?;
    require(
        target == native.target,
        "native execution required for artifact qualification",
    )?;
    let temporary = tempfile::Builder::new()
        .prefix("inframeld verification with spaces ")
        .tempdir()?;
    let root = temporary.path();
    let home = root.join("home");
    fs::create_dir(&home)?;
    let sentinels = [
        ".config/inframeld/targets",
        ".config/inframeld/credentials",
        "installation/data",
        ".profile",
    ];
    for name in sentinels {
        let path = home.join(name);
        fs::create_dir_all(
            path.parent()
                .ok_or_else(|| Error::Invalid("sentinel path".into()))?,
        )?;
        fs::write(path, b"preserve me")?;
    }
    let mut before = BTreeMap::new();
    snapshot(&home, &home, &mut before)?;
    let binary = root.join("inframeld");
    for entry in archive::read(path)? {
        if entry
            .path
            .file_name()
            .is_some_and(|name| name == "inframeld")
        {
            fs::write(&binary, entry.bytes)?;
        }
    }
    let installed = home.join(".local/bin/inframeld");
    install(&binary, &installed)?;
    require(
        install(&binary, &installed).is_err(),
        "existing executable was replaced",
    )?;
    require(
        archive::digest(&binary)? == archive::digest(&installed)?,
        "installed executable changed",
    )?;
    let blocked = root.join("not-a-directory");
    fs::write(&blocked, b"preserve")?;
    require(
        install(&binary, &blocked.join("bin/inframeld")).is_err()
            && fs::read(&blocked)? == b"preserve",
        "blocked destination modified state",
    )?;
    let denied = root.join("read-only-bin");
    fs::create_dir(&denied)?;
    fs::set_permissions(&denied, fs::Permissions::from_mode(0o555))?;
    let denied_result = install(&binary, &denied.join("inframeld"));
    fs::set_permissions(&denied, fs::Permissions::from_mode(0o755))?;
    // Qualifying as root would make permission-denial evidence meaningless.
    require(
        denied_result.is_err(),
        "permission-denial check requires an unprivileged user",
    )?;
    for args in [&[][..], &["--help"][..], &["version", "--help"][..]] {
        require(
            !execute(&installed, &home, args)?.is_empty(),
            "empty help output",
        )?;
    }
    require(
        execute(&installed, &home, &["version"])? == metadata.render(),
        "binary and packaged metadata disagree",
    )?;
    let binary_sha256 = archive::digest(&installed)?;
    fs::remove_file(&installed)?;
    for name in sentinels {
        require(
            fs::read(home.join(name))? == b"preserve me",
            "user state changed",
        )?;
    }
    let mut after = BTreeMap::new();
    snapshot(&home, &home, &mut after)?;
    require(
        before == after,
        "user state changed during installation or execution",
    )?;
    require(!installed.exists(), "executable removal failed")?;
    Ok(Evidence {
        archive_sha256: archive::digest(path)?,
        binary_sha256,
        metadata,
        permission_denial_checked: true,
    })
}
