//! The same typed build information drives terminal output and package evidence.
use serde::{Deserialize, Serialize};

/// Build identity and the approved support policy, rather than remote verification.
#[derive(Debug, Clone, PartialEq, Eq, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct BuildMetadata {
    pub schema_version: u32,
    pub policy: String,
    pub cli_version: String,
    pub qualified_runtime: Option<String>,
    pub remote_verification: String,
    pub status: String,
    pub revision: String,
    pub target: String,
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
    /// # Errors
    /// Rejects invalid build metadata before it can become a support claim.
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
