//! The same typed build information drives terminal output and package evidence.
use serde::{Deserialize, Serialize};

/// Build identity and the approved support policy, rather than remote verification.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BuildMetadata {
    /// Version of the embedded metadata representation.
    pub schema_version: u32,
    /// Approved CLI/runtime pairing policy from the compatibility descriptor.
    pub policy: String,
    /// CLI package version recorded by the build.
    pub cli_version: String,
    /// Explicitly qualified runtime release, absent for the development profile.
    pub qualified_runtime: Option<String>,
    /// Availability of remote compatibility verification, not its successful result.
    pub remote_verification: String,
    /// Development or release status asserted by the validated metadata.
    pub status: String,
    /// Source revision, or `unknown` when source identity was unavailable.
    pub revision: String,
    /// Rust target triple of the executable described by this build.
    pub target: String,
    /// Whether the build's source inputs were recorded as locally modified.
    pub source_dirty: bool,
}

impl BuildMetadata {
    /// Validate supported development metadata without silently accepting a release claim.
    ///
    /// # Errors
    /// Rejects malformed metadata or unqualified compatibility assertions.
    pub fn parse(bytes: &[u8]) -> Result<Self, String> {
        let metadata: Self = serde_json::from_slice(bytes).map_err(|error| error.to_string())?;
        if metadata.schema_version != 1
            || metadata.policy != "matching-qualified-releases"
            || metadata.status != "development"
            || metadata.qualified_runtime.is_some()
            || metadata.remote_verification != "unavailable"
            || metadata.cli_version.is_empty()
            || metadata.target.is_empty()
            || !(metadata.revision == "unknown"
                || metadata.revision.len() == 40
                    && metadata
                        .revision
                        .bytes()
                        .all(|byte| byte.is_ascii_hexdigit()))
        {
            return Err("unsupported or unqualified build metadata".into());
        }
        Ok(metadata)
    }

    /// Read the metadata generated from the descriptor and Cargo build identity.
    ///
    /// This reads embedded bytes without contacting an installation. A supported
    /// development descriptor still has no qualified runtime release.
    ///
    /// # Errors
    /// Rejects invalid build metadata before it can become a support claim.
    ///
    /// # Examples
    /// ```
    /// use inframeld_cli::metadata::BuildMetadata;
    ///
    /// # fn main() -> Result<(), String> {
    /// let metadata = BuildMetadata::embedded()?;
    /// assert!(metadata.qualified_runtime.is_none());
    /// assert!(!metadata.cli_version.is_empty());
    /// # Ok(())
    /// # }
    /// ```
    pub fn embedded() -> Result<Self, String> {
        Self::parse(include_bytes!(concat!(
            env!("OUT_DIR"),
            "/compatibility.json"
        )))
    }

    /// Render the same facts used by package verification.
    #[must_use]
    pub fn render(&self) -> String {
        format!(
            "inframeld {}\nDevelopment build\nRevision: {}\nSource dirty: {}\nTarget: {}\nQualified runtime: {}\nPolicy: matching qualified releases only\nRemote compatibility: unverified\n",
            self.cli_version,
            self.revision,
            self.source_dirty,
            self.target,
            self.qualified_runtime.as_deref().unwrap_or("none")
        )
    }
}
