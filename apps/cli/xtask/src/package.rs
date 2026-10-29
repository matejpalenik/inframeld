//! Build and qualify native packages using explicit workspace and source inputs.
//!
//! The same operation produces local and CI evidence. It never publishes a release.
//! Dynamic JSON is confined to Cargo and cargo-dist message boundaries.

use crate::{Error, Result, archive, process, verify};
use inframeld_cli::metadata::BuildMetadata;
use serde_json::Value;
use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
};

/// Build, stamp, normalize and qualify through the same path locally and in CI.
///
/// Records source/build identity and development qualification evidence. Optional
/// reproducibility compares two builds using the same resolved inputs. Failed
/// operations may leave build artifacts and earlier evidence for inspection.
///
/// # Errors
/// Missing tools, invalid metadata and every failed verification gate abort the task.
pub fn run(target: Option<String>, reproducible: bool) -> Result<()> {
    ensure_packaging_tool()?;
    let context = PackagingContext::resolve(target)?;
    let first = context.build()?;
    let evidence_dir = context.root.join("target/cli-evidence");
    fs::create_dir_all(&evidence_dir)?;
    fs::write(
        evidence_dir.join("first.json"),
        serde_json::to_vec_pretty(&first)?,
    )?;
    if reproducible {
        process::checked(context.command("cargo").args([
            "clean",
            "-p",
            "inframeld-cli",
            "--profile",
            "dist",
            "--target",
            &context.target,
        ]))?;
        let second = context.build()?;
        fs::write(
            evidence_dir.join("second.json"),
            serde_json::to_vec_pretty(&second)?,
        )?;
        verify::compare(&first, &second)?;
    }
    let compiler = process::checked(context.command("rustc").args(["--version", "--verbose"]))?;
    fs::write(evidence_dir.join("compiler.txt"), compiler.stdout)?;
    println!("{}", serde_json::to_string_pretty(&first)?);
    Ok(())
}

/// Resolved inputs shared by build commands and optional repeated qualification.
#[derive(Debug)]
struct PackagingContext {
    root: PathBuf,
    target: String,
    epoch: u64,
    revision: String,
    dirty: bool,
    package_id: String,
}

impl PackagingContext {
    /// Resolve current workspace and build inputs after tool admission.
    fn resolve(target: Option<String>) -> Result<Self> {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../..")
            .canonicalize()?;
        let native = BuildMetadata::embedded().map_err(Error::Invalid)?;
        let target = target.unwrap_or(native.target.clone());
        if !matches!(
            target.as_str(),
            "aarch64-apple-darwin"
                | "x86_64-apple-darwin"
                | "aarch64-unknown-linux-gnu"
                | "x86_64-unknown-linux-gnu"
        ) || target != native.target
        {
            return Err(Error::Invalid(
                "packaging qualification requires a supported native target".into(),
            ));
        }
        let revision = git(&root, &["rev-parse", "HEAD"])?.trim().to_owned();
        let epoch = git(&root, &["show", "-s", "--format=%ct", "HEAD"])?
            .trim()
            .parse()
            .map_err(|_| Error::Invalid("invalid source epoch".into()))?;
        let dirty = !git(
            &root,
            &["status", "--porcelain", "--untracked-files=normal"],
        )?
        .trim()
        .is_empty();
        let cargo = process::checked(Command::new("cargo").current_dir(&root).args([
            "metadata",
            "--locked",
            "--no-deps",
            "--format-version=1",
        ]))?;
        let cargo: Value = serde_json::from_slice(&cargo.stdout)?;
        let package_id = cargo["packages"]
            .as_array()
            .and_then(|packages| {
                packages
                    .iter()
                    .find(|package| package["name"] == "inframeld-cli")
            })
            .and_then(|package| package["id"].as_str())
            .ok_or_else(|| Error::Invalid("CLI missing from Cargo workspace".into()))?
            .to_owned();
        Ok(Self {
            root,
            target,
            epoch,
            revision,
            dirty,
            package_id,
        })
    }

    /// Apply the same source identity and native-target settings to build commands.
    fn command(&self, program: &str) -> Command {
        let mut command = Command::new(program);
        command
            .current_dir(&self.root)
            .env("SOURCE_DATE_EPOCH", self.epoch.to_string())
            .env("INFRAMELD_BUILD_REVISION", &self.revision)
            .env("INFRAMELD_BUILD_DIRTY", self.dirty.to_string())
            .env(
                "RUSTFLAGS",
                format!("--remap-path-prefix={}=/inframeld", self.root.display()),
            );
        if self.target.ends_with("apple-darwin") {
            command.env("MACOSX_DEPLOYMENT_TARGET", "13.0");
        }
        command
    }

    /// Build, stamp and verify one archive before recording its manifest.
    fn build(&self) -> Result<verify::Evidence> {
        process::checked(self.command("dist").args([
            "build",
            "--artifacts=local",
            "--target",
            &self.target,
        ]))?;
        // Cargo reports the exact OUT_DIR containing the CLI's embedded metadata.
        let output = process::checked(self.command("cargo").args([
            "build",
            "--locked",
            "-p",
            "inframeld-cli",
            "--profile",
            "dist",
            "--target",
            &self.target,
            "--message-format=json",
        ]))?;
        let bytes = embedded_build_metadata(&output.stdout, &self.package_id)?;
        let parsed = BuildMetadata::parse(&bytes).map_err(Error::Invalid)?;
        if parsed.revision != self.revision
            || parsed.source_dirty != self.dirty
            || parsed.target != self.target
        {
            return Err(Error::Invalid(
                "build metadata does not match packaging inputs".into(),
            ));
        }
        let archive = self.root.join(format!(
            "target/distrib/inframeld-cli-{}.tar.xz",
            self.target
        ));
        archive::stamp(&archive, self.epoch, &bytes)?;
        let evidence = verify::artifact(&archive, &self.target)?;
        let manifest = process::checked(self.command("dist").args([
            "manifest",
            "--artifacts=local",
            "--target",
            &self.target,
            "--output-format=json",
            "--no-local-paths",
        ]))?;
        fs::write(
            self.root
                .join(format!("target/distrib/manifest-{}.json", self.target)),
            manifest.stdout,
        )?;
        Ok(evidence)
    }
}

/// Require the pinned build tool before resolving inputs or starting a build.
fn ensure_packaging_tool() -> Result<()> {
    let version = process::checked(Command::new("dist").arg("--version"))
        .map_err(|_|Error::Invalid("Packaging requires cargo-dist 0.33.0. Run cargo install --locked --version 0.33.0 cargo-dist and add its bin directory to PATH.".into()))?;
    if String::from_utf8_lossy(&version.stdout).trim() != "cargo-dist 0.33.0" {
        return Err(Error::Invalid(
            "Packaging requires cargo-dist 0.33.0".into(),
        ));
    }
    Ok(())
}

fn git(root: &Path, arguments: &[&str]) -> Result<String> {
    let output = process::checked(Command::new("git").current_dir(root).args(arguments))?;
    String::from_utf8(output.stdout)
        .map_err(|_| Error::Invalid("Git returned invalid UTF-8".into()))
}

/// Read the exact embedded metadata reported by this CLI build-script invocation.
fn embedded_build_metadata(output: &[u8], package_id: &str) -> Result<Vec<u8>> {
    let mut metadata = None;
    for line in output
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
    {
        let message: Value = serde_json::from_slice(line)?;
        if message["reason"] == "build-script-executed" && message["package_id"] == package_id {
            let out_dir = message["out_dir"]
                .as_str()
                .ok_or_else(|| Error::Invalid("Cargo omitted build output directory".into()))?;
            metadata = Some(fs::read(Path::new(out_dir).join("compatibility.json"))?);
        }
    }
    metadata.ok_or_else(|| Error::Invalid("Cargo did not report CLI metadata".into()))
}
