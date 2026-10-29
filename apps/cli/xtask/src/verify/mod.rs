//! Inspect archives before qualifying native execution in disposable directories.
//!
//! Inspection validates payload and build identity without executing the binary.
//! Native qualification additionally tests installation, offline invocation and
//! preserved user state. Checksums alone do not authenticate an artifact's publisher.

mod inspect;
mod native;

use inframeld_cli::metadata::BuildMetadata;
use serde::{Deserialize, Serialize};

use crate::{Error, Result};

pub use inspect::inspect;
pub use native::{artifact, install};

/// Native qualification facts. A successful read never substitutes for these checks.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct Evidence {
    /// SHA-256 of the qualified normalized archive bytes.
    pub archive_sha256: String,
    /// SHA-256 of the installed executable used for native checks.
    pub binary_sha256: String,
    /// Validated build identity shared with the executable's version output.
    pub metadata: BuildMetadata,
    /// Whether installation into a denied destination failed as an unprivileged user.
    pub permission_denial_checked: bool,
}

/// Compare successful independent builds using checks that remain active in release mode.
///
/// # Errors
/// Any differing archive, executable or build identity fails reproducibility.
pub fn compare(first: &Evidence, second: &Evidence) -> Result<()> {
    require(first == second, "repeated builds differ")
}
/// Keep every verification gate active in both debug and optimized builds.
fn require(condition: bool, message: &str) -> Result<()> {
    if condition {
        Ok(())
    } else {
        Err(Error::Invalid(message.into()))
    }
}
