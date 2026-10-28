use std::{env, fs, path::PathBuf, process::Command};

fn git(arguments: &[&str]) -> Option<String> {
    Command::new("git")
        .args(arguments)
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    for variable in ["INFRAMELD_BUILD_REVISION", "INFRAMELD_BUILD_DIRTY"] {
        println!("cargo:rerun-if-env-changed={variable}");
    }
    for path in [
        "compatibility.json",
        "../../.git/HEAD",
        "../../.git/index",
        "../../.git/refs/heads",
        "../../.git/packed-refs",
    ] {
        println!("cargo:rerun-if-changed={path}");
    }
    let revision = env::var("INFRAMELD_BUILD_REVISION")
        .ok()
        .or_else(|| git(&["rev-parse", "HEAD"]))
        .unwrap_or_else(|| "unknown".to_owned());
    let revision = revision.trim();
    let revision = if revision.len() == 40 && revision.bytes().all(|b| b.is_ascii_hexdigit()) {
        revision
    } else {
        "unknown"
    };
    let dirty = match env::var("INFRAMELD_BUILD_DIRTY") {
        Ok(value) => value.parse::<bool>()?,
        Err(_) => git(&["status", "--porcelain", "--untracked-files=normal"])
            .is_none_or(|status| !status.trim().is_empty()),
    };
    let mut metadata: serde_json::Value = serde_json::from_slice(&fs::read("compatibility.json")?)?;
    metadata["cliVersion"] = env::var("CARGO_PKG_VERSION")?.into();
    metadata["revision"] = revision.into();
    metadata["target"] = env::var("TARGET")?.into();
    metadata["sourceDirty"] = dirty.into();
    fs::write(
        PathBuf::from(env::var("OUT_DIR")?).join("compatibility.json"),
        serde_json::to_vec_pretty(&metadata)?,
    )?;
    Ok(())
}
