//! Reject false compatibility claims in embedded build metadata.

// Fixtures and assertions deliberately fail immediately on invalid expectations.
#![allow(clippy::unwrap_used)]
use inframeld_cli::metadata::BuildMetadata;
use serde_json::json;

#[test]
fn metadata_rejects_unqualified_claims_in_all_build_profiles() {
    let valid = json!({"schemaVersion":1,"policy":"matching-qualified-releases","cliVersion":"0.0.0","qualifiedRuntime":null,"remoteVerification":"unavailable","status":"development","revision":"unknown","target":"aarch64-apple-darwin","sourceDirty":true});
    assert!(BuildMetadata::parse(&serde_json::to_vec(&valid).unwrap()).is_ok());
    for (field, value) in [
        ("status", json!("released")),
        ("qualifiedRuntime", json!("unqualified")),
        ("policy", json!("anything")),
        ("schemaVersion", json!(2)),
        ("remoteVerification", json!("verified")),
    ] {
        let mut invalid = valid.clone();
        invalid[field] = value;
        assert!(BuildMetadata::parse(&serde_json::to_vec(&invalid).unwrap()).is_err());
    }
}
