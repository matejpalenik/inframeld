//! Present embedded build information through the shared metadata representation.

use crate::metadata::BuildMetadata;
use serde::Serialize;

/// Distinguish invalid embedded information from a bounded-output rejection.
#[derive(Debug, Clone, Copy)]
pub(crate) enum VersionError {
    InvalidMetadata,
    OutputLimit,
}

/// Read embedded information without establishing remote runtime compatibility.
pub(crate) fn execute() -> Result<BuildMetadata, VersionError> {
    BuildMetadata::embedded().map_err(|_| VersionError::InvalidMetadata)
}

/// Serialize the reviewed CLI leaf, independently of the metadata file schema.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct VersionData<'a> {
    cli_version: &'a str,
    revision: Option<&'a str>,
    source_dirty: bool,
    target: &'a str,
    qualified_runtime: Option<&'a str>,
    policy: &'static str,
    build_status: &'static str,
    remote_verification: &'static str,
    remote_compatibility: &'static str,
}

/// Preserve unknown source identity without widening the validated support claim.
pub(crate) fn data(metadata: &BuildMetadata) -> Result<VersionData<'_>, VersionError> {
    if metadata.cli_version.len() > 128 || metadata.target.len() > 256 {
        return Err(VersionError::OutputLimit);
    }
    Ok(VersionData {
        cli_version: &metadata.cli_version,
        revision: (metadata.revision != "unknown").then_some(metadata.revision.as_str()),
        source_dirty: metadata.source_dirty,
        target: &metadata.target,
        qualified_runtime: None,
        policy: "matching-qualified-releases",
        build_status: "development",
        remote_verification: "unavailable",
        remote_compatibility: "unverified",
    })
}

/// Describe the offline read without reading the embedded values themselves.
#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub(crate) struct VersionPlan {
    command: &'static str,
    intended_reads: [&'static str; 1],
    intended_destination: &'static str,
    outgoing_data_categories: [&'static str; 2],
    intended_effects: [&'static str; 1],
    checks_performed: [&'static str; 1],
    unresolved_choices: [&'static str; 0],
    operation_performed: bool,
}

/// Explain only parser-validated intent, with no embedded value observation.
pub(crate) fn plan() -> VersionPlan {
    VersionPlan {
        command: "version",
        intended_reads: ["embeddedBuildMetadata"],
        intended_destination: "stdout",
        outgoing_data_categories: ["buildIdentity", "compatibilityPolicy"],
        intended_effects: ["writeVersionInformationToStdout"],
        checks_performed: ["argumentsValidated"],
        unresolved_choices: [],
        operation_performed: false,
    }
}

/// Keep the explanation distinct from a completed version observation.
pub(crate) const HUMAN_PLAN: &str = "Version dry-run\nIntended read: embedded build metadata\nIntended destination: stdout\nOutgoing data: build identity and compatibility policy\nIntended effect: write version information to stdout\nChecks performed: arguments validated\nUnresolved choices: none\nEmbedded values were not read.\nRemote compatibility was not checked.\nNo product operation was performed.\n";

#[cfg(test)]
mod tests {
    // Metadata fixtures and observable serialization assertions fail directly.
    #![allow(clippy::unwrap_used)]

    use super::{VersionError, data};
    use crate::metadata::BuildMetadata;

    #[test]
    fn unknown_revision_is_null_without_erasing_the_dirty_source_observation() {
        let mut metadata = BuildMetadata::embedded().unwrap();
        metadata.revision = "unknown".into();
        metadata.source_dirty = true;
        let value = serde_json::to_value(data(&metadata).unwrap()).unwrap();
        assert!(value["revision"].is_null());
        assert_eq!(value["sourceDirty"], true);
        assert!(value["qualifiedRuntime"].is_null());
        assert_eq!(value["remoteCompatibility"], "unverified");
    }

    #[test]
    fn cli_scalar_limits_use_utf8_bytes_and_preserve_boundary_values() {
        let mut metadata = BuildMetadata::embedded().unwrap();
        metadata.cli_version = "é".repeat(64);
        metadata.target = "t".repeat(256);
        assert!(data(&metadata).is_ok());
        metadata.cli_version.push('x');
        assert!(matches!(data(&metadata), Err(VersionError::OutputLimit)));
        metadata.cli_version = "0.0.0".into();
        metadata.target.push('x');
        assert!(matches!(data(&metadata), Err(VersionError::OutputLimit)));
    }
}
