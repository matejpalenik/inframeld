//! Validate the reviewed repair intent before any browser, provider or child effect.

use serde::{Deserialize, Serialize};
use uuid::Uuid;

/// A proof-free request for an already-admitted Project metadata recipient.
#[derive(Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RepairRequest {
    schema_version: u8,
    mode: RepairMode,
    pub(super) expected_installation_id: Uuid,
    pub(super) operation_id: String,
    operator_label: String,
    reason: String,
    pub(super) expected_access_revision: i64,
    pub(super) expected_identity_id: Uuid,
    pub(super) responsibility: MetadataResponsibility,
}

impl std::fmt::Debug for RepairRequest {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("RepairRequest([reviewed intent])")
    }
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
enum RepairMode {
    #[serde(rename = "repair-stranded-authority")]
    RepairStrandedAuthority,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(super) struct MetadataResponsibility {
    kind: GrantorKind,
    target: ProjectTarget,
    action_id: MetadataAction,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
enum GrantorKind {
    #[serde(rename = "action-grantor")]
    ActionGrantor,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct ProjectTarget {
    kind: ProjectKind,
    project_id: Uuid,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
enum ProjectKind {
    #[serde(rename = "project")]
    Project,
}

#[derive(Debug, Deserialize, Serialize, PartialEq, Eq)]
enum MetadataAction {
    #[serde(rename = "edit-project-metadata")]
    EditProjectMetadata,
}

/// Transient recipient proof constructed only by the verified authorization flow.
///
/// Tokens remain opaque and have no public serialization or access operation.
pub struct RecipientProof {
    pub(super) access_token: zeroize::Zeroizing<String>,
    pub(super) installation_id: Uuid,
    pub(super) identity_id: Uuid,
    pub(super) principal_id: Uuid,
}

impl std::fmt::Debug for RecipientProof {
    fn fmt(&self, formatter: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        formatter.write_str("RecipientProof([redacted])")
    }
}

/// Invalid repair input is rejected without disclosing its protected content.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
#[error("The proof-free repair request is invalid or unsupported.")]
pub struct InvalidRepairRequest;

/// A maintenance result accepted only after matching the original reviewed binding.
#[derive(Debug, Deserialize, Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RepairReceipt {
    schema_version: u8,
    mode: RepairMode,
    operation_id: String,
    installation_id: Uuid,
    principal_id: Uuid,
    access_revision: i64,
    outcome: RepairOutcome,
    responsibility: MetadataResponsibility,
}

#[derive(Debug, Deserialize, Serialize)]
enum RepairOutcome {
    #[serde(rename = "repaired")]
    Repaired,
}

/// A response without a matching after-commit receipt cannot prove completion.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
#[error("The maintenance response did not prove the original operation's outcome.")]
pub struct InvalidReceipt;

impl RepairRequest {
    /// Read exactly one bounded request, excluding bootstrap and supplied proof.
    ///
    /// # Errors
    /// Rejects unknown/duplicate fields, invalid scalars and unsupported intent.
    pub fn parse(bytes: &[u8]) -> Result<Self, InvalidRepairRequest> {
        if bytes.len() > 65_536 {
            return Err(InvalidRepairRequest);
        }
        let request: Self = serde_json::from_slice(bytes).map_err(|_| InvalidRepairRequest)?;
        if request.schema_version != 1
            || request.expected_access_revision < 0
            || !valid_text(&request.operation_id, 128)
            || !valid_text(&request.operator_label, 128)
            || !valid_text(&request.reason, 512)
        {
            return Err(InvalidRepairRequest);
        }
        Ok(request)
    }

    /// Validate a bounded after-commit receipt against this request and verified session.
    ///
    /// # Errors
    /// Rejects malformed, duplicate, unknown or mismatched receipt data.
    pub fn validate_receipt(
        &self,
        bytes: &[u8],
        principal_id: Uuid,
    ) -> Result<RepairReceipt, InvalidReceipt> {
        if bytes.len() > 65_536 {
            return Err(InvalidReceipt);
        }
        let receipt: RepairReceipt = serde_json::from_slice(bytes).map_err(|_| InvalidReceipt)?;
        if receipt.schema_version != 1
            || receipt.operation_id != self.operation_id
            || receipt.installation_id != self.expected_installation_id
            || receipt.principal_id != principal_id
            || Some(receipt.access_revision) != self.expected_access_revision.checked_add(1)
            || receipt.responsibility != self.responsibility
        {
            return Err(InvalidReceipt);
        }
        Ok(receipt)
    }

    /// Correlate an uncertain outcome with this original reviewed operation.
    #[must_use]
    pub fn operation_id(&self) -> &str {
        &self.operation_id
    }
}

/// Python's string whitespace includes the four information separators that
/// Rust's Unicode whitespace predicate excludes. Validation never trims values.
fn valid_text(value: &str, limit: usize) -> bool {
    !value.contains('\0')
        && value.chars().count() <= limit
        && value.chars().any(|character| {
            !character.is_whitespace() && !('\u{001c}'..='\u{001f}').contains(&character)
        })
}

#[cfg(test)]
mod tests {
    #![allow(clippy::unwrap_used)]
    use super::*;

    fn request() -> serde_json::Value {
        serde_json::json!({
            "schemaVersion":1,"mode":"repair-stranded-authority",
            "expectedInstallationId":"00000000-0000-0000-0000-000000000001",
            "operationId":" reviewed-operation ","operatorLabel":" Alice ","reason":" repair reviewed authority ",
            "expectedAccessRevision":4,
            "expectedIdentityId":"00000000-0000-0000-0000-000000000002",
            "responsibility":{"kind":"action-grantor","target":{"kind":"project","projectId":"00000000-0000-0000-0000-000000000003"},"actionId":"edit-project-metadata"}
        })
    }

    #[test]
    fn accepts_only_the_reviewed_bounded_repair_intent_with_python_text_semantics() {
        assert!(RepairRequest::parse(&serde_json::to_vec(&request()).unwrap()).is_ok());
        for field in ["operationId", "operatorLabel", "reason"] {
            for blank in [
                "",
                " \t\r\n",
                "\u{001c}\u{001d}\u{001e}\u{001f}",
                "\u{0085}\u{00a0}\u{2003}\u{3000}",
            ] {
                let mut value = request();
                value[field] = blank.into();
                assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_err());
            }
            let mut value = request();
            value[field] = "valid\u{001c}text".into();
            assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_ok());
            let mut value = request();
            value[field] = "nul\0value".into();
            assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_err());
            let limit = if field == "reason" { 512 } else { 128 };
            let mut value = request();
            value[field] = "é".repeat(limit).into();
            assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_ok());
            value[field] = "é".repeat(limit + 1).into();
            assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_err());
        }
        for field in ["schemaVersion", "expectedAccessRevision"] {
            for scalar in [
                serde_json::json!(true),
                serde_json::json!(1.0),
                serde_json::json!("1"),
                serde_json::json!(-1),
            ] {
                let mut value = request();
                value[field] = scalar;
                assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_err());
            }
        }
        let mut value = request();
        value["mode"] = "bootstrap-first-administrator".into();
        assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_err());
        let mut value = request();
        value["identityProof"] =
            serde_json::json!({"kind":"hydra-access-token","accessToken":"never-accepted"});
        assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_err());
        let mut value = request();
        value["responsibility"]["target"]["extra"] = true.into();
        assert!(RepairRequest::parse(&serde_json::to_vec(&value).unwrap()).is_err());
        let json = serde_json::to_string(&request()).unwrap();
        assert!(RepairRequest::parse(format!("{json} {json}").as_bytes()).is_err());
        let duplicate = json.replacen(
            "\"schemaVersion\":1",
            "\"schemaVersion\":1,\"schemaVersion\":1",
            1,
        );
        assert!(RepairRequest::parse(duplicate.as_bytes()).is_err());
        let duplicate = json.replacen(
            "\"kind\":\"project\"",
            "\"kind\":\"project\",\"kind\":\"project\"",
            1,
        );
        assert!(RepairRequest::parse(duplicate.as_bytes()).is_err());
    }

    #[test]
    fn receipt_must_prove_the_original_request_and_verified_session_without_rebinding() {
        let input = request();
        let request = RepairRequest::parse(&serde_json::to_vec(&input).unwrap()).unwrap();
        let principal = Uuid::from_u128(10);
        let receipt = serde_json::json!({
            "schemaVersion":1,"mode":"repair-stranded-authority",
            "operationId":input["operationId"],"installationId":input["expectedInstallationId"],
            "principalId":principal,"accessRevision":5,"outcome":"repaired", "responsibility":input["responsibility"]
        });
        assert!(
            request
                .validate_receipt(&serde_json::to_vec(&receipt).unwrap(), principal)
                .is_ok()
        );
        for (field, value) in [
            ("operationId", serde_json::json!("different-operation")),
            ("installationId", serde_json::json!(Uuid::from_u128(99))),
            ("principalId", serde_json::json!(Uuid::from_u128(99))),
            ("accessRevision", serde_json::json!(6)),
            ("accessRevision", serde_json::json!(5.0)),
            ("outcome", serde_json::json!("failed")),
            ("extra", serde_json::json!("protected-token-sentinel")),
        ] {
            let mut mismatched = receipt.clone();
            mismatched[field] = value;
            let error = request
                .validate_receipt(&serde_json::to_vec(&mismatched).unwrap(), principal)
                .unwrap_err();
            assert!(!format!("{error:?} {error}").contains("protected-token-sentinel"));
        }
        let mut mismatched = receipt.clone();
        mismatched["responsibility"]["target"]["projectId"] =
            serde_json::json!(Uuid::from_u128(99));
        assert!(
            request
                .validate_receipt(&serde_json::to_vec(&mismatched).unwrap(), principal)
                .is_err()
        );
        let json = serde_json::to_string(&receipt).unwrap();
        let duplicate = json.replacen(
            "\"schemaVersion\":1",
            "\"schemaVersion\":1,\"schemaVersion\":1",
            1,
        );
        assert!(
            request
                .validate_receipt(duplicate.as_bytes(), principal)
                .is_err()
        );
    }
}
