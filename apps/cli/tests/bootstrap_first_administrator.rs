//! Check the proof-free bootstrap boundary independently of browser or host effects.

#![allow(clippy::unwrap_used)]

use inframeld_cli::auth::recipient_proof::{BootstrapRequest, RepairRequest};
use serde_json::{Value, json};

fn request() -> Value {
    json!({
        "schemaVersion": 1,
        "mode": "bootstrap-first-administrator",
        "expectedInstallationId": "00000000-0000-0000-0000-000000000001",
        "operationId": "original-bootstrap",
        "operatorLabel": "Host operator",
        "reason": "Reviewed first admission",
        "expectedAccessRevision": 0,
        "expectedIdentityId": "00000000-0000-0000-0000-000000000002"
    })
}

#[test]
fn accepts_valid_proof_free_bootstrap_intent() {
    assert!(BootstrapRequest::parse(&serde_json::to_vec(&request()).unwrap()).is_ok());
}

#[test]
fn repair_input_still_rejects_bootstrap_intent() {
    assert!(RepairRequest::parse(&serde_json::to_vec(&request()).unwrap()).is_err());
}

#[test]
fn rejects_unsupported_schema_mode_and_nonzero_or_noninteger_revision() {
    for (field, invalid) in [
        ("schemaVersion", json!([0, 2, true, null, "1", 1.0])),
        (
            "mode",
            json!(["repair-stranded-authority", "bootstrap", true, null]),
        ),
        (
            "expectedAccessRevision",
            json!([-1, 1, 9_007_199_254_740_992_i64, 0.0, true, "0", null]),
        ),
    ] {
        for value in invalid.as_array().unwrap() {
            let mut input = request();
            input[field] = value.clone();
            assert!(BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).is_err());
        }
    }
}

#[test]
fn rejects_missing_fields_and_supplied_proof_or_responsibility() {
    for field in [
        "schemaVersion",
        "mode",
        "expectedInstallationId",
        "operationId",
        "operatorLabel",
        "reason",
        "expectedAccessRevision",
        "expectedIdentityId",
    ] {
        let mut input = request();
        input.as_object_mut().unwrap().remove(field);
        assert!(BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).is_err());
    }
    for (field, value) in [
        (
            "identityProof",
            json!({"kind": "hydra-access-token", "accessToken": "SUPPLIED-PROOF"}),
        ),
        ("responsibility", json!(null)),
        ("extra", json!(true)),
    ] {
        let mut input = request();
        input[field] = value;
        assert!(BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).is_err());
    }
}

#[test]
fn rejects_duplicate_keys_and_a_second_json_value() {
    let original = serde_json::to_string(&request()).unwrap();
    for field in [
        "operationId",
        "expectedIdentityId",
        "expectedAccessRevision",
    ] {
        let value = serde_json::to_string(&request()[field]).unwrap();
        let duplicate = format!("{{\"{field}\":{value},{}", &original[1..]);
        assert!(BootstrapRequest::parse(duplicate.as_bytes()).is_err());
    }
    assert!(BootstrapRequest::parse(format!("{original} {original}").as_bytes()).is_err());
}

#[test]
fn requires_uuid_installation_and_candidate_identifiers() {
    for field in ["expectedInstallationId", "expectedIdentityId"] {
        for value in [
            json!("not-uuid"),
            json!(""),
            json!(null),
            json!(17),
            json!(false),
        ] {
            let mut input = request();
            input[field] = value;
            assert!(BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).is_err());
        }
    }
}

#[test]
fn preserves_original_meaning_without_exposing_review_details_in_debug() {
    let mut input = request();
    input["operationId"] = json!(" original-bootstrap ");
    input["operatorLabel"] = json!(" PRIVATE-OPERATOR ");
    input["reason"] = json!(" PRIVATE-REVIEW-REASON ");
    let parsed = BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).unwrap();
    assert_eq!(serde_json::to_value(&parsed).unwrap(), input);
    assert_eq!(format!("{parsed:?}"), "BootstrapRequest([reviewed intent])");
}

#[test]
fn accepts_native_character_limits_and_rejects_one_character_more() {
    for (field, limit) in [
        ("operationId", 128),
        ("operatorLabel", 128),
        ("reason", 512),
    ] {
        let mut input = request();
        input[field] = json!("é".repeat(limit));
        assert!(BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).is_ok());
        input[field] = json!("é".repeat(limit + 1));
        assert!(BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).is_err());
    }
}

#[test]
fn rejects_blank_python_whitespace_and_embedded_nul_text() {
    for field in ["operationId", "operatorLabel", "reason"] {
        for value in ["", " \t\r\n", "\u{001c}\u{001f}", "left\0right"] {
            let mut input = request();
            input[field] = json!(value);
            assert!(BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).is_err());
        }
    }
}

#[test]
fn bounds_the_wire_bytes_and_rejects_invalid_json_encoding() {
    let mut input = serde_json::to_vec(&request()).unwrap();
    input.resize(65_536, b' ');
    assert!(BootstrapRequest::parse(&input).is_ok());
    input.push(b' ');
    assert!(BootstrapRequest::parse(&input).is_err());
    let invalid: &[&[u8]] = &[b"\xff", b"{", b"null", b"[]"];
    for bytes in invalid {
        assert!(BootstrapRequest::parse(bytes).is_err());
    }
}

#[test]
fn invalid_input_diagnostics_do_not_echo_supplied_proof() {
    let mut input = request();
    input["identityProof"] = json!({
        "kind": "hydra-access-token",
        "accessToken": "PRIVATE-SUPPLIED-PROOF"
    });
    let failure = BootstrapRequest::parse(&serde_json::to_vec(&input).unwrap()).unwrap_err();
    assert_eq!(
        failure.to_string(),
        "The proof-free bootstrap request is invalid or unsupported."
    );
    assert_eq!(format!("{failure:?}"), "InvalidBootstrapRequest");
}

#[test]
fn bootstrap_receipt_requires_exact_original_binding_and_closed_wire_shape() {
    let request = BootstrapRequest::parse(&serde_json::to_vec(&request()).unwrap()).unwrap();
    let receipt = serde_json::json!({
        "schemaVersion":1,"mode":"bootstrap-first-administrator",
        "operationId":"original-bootstrap", "installationId":"00000000-0000-0000-0000-000000000001",
        "principalId":"00000000-0000-0000-0000-00000000000a", "accessRevision":1,"outcome":"bootstrapped"
    });
    assert!(
        request
            .validate_receipt(&serde_json::to_vec(&receipt).unwrap())
            .is_ok()
    );
    for (field, value) in [
        ("schemaVersion", serde_json::json!(2)),
        ("mode", serde_json::json!("repair-stranded-authority")),
        ("operationId", serde_json::json!("other")),
        (
            "installationId",
            serde_json::json!("00000000-0000-0000-0000-000000000099"),
        ),
        ("principalId", serde_json::json!("invalid")),
        ("accessRevision", serde_json::json!(2)),
        ("outcome", serde_json::json!("repaired")),
        ("responsibility", serde_json::json!({})),
    ] {
        let mut invalid = receipt.clone();
        invalid[field] = value;
        assert!(
            request
                .validate_receipt(&serde_json::to_vec(&invalid).unwrap())
                .is_err(),
            "{field}"
        );
    }
    assert!(request.validate_receipt(b"{}").is_err());
    assert!(request.validate_receipt(&vec![b' '; 65_537]).is_err());
}

#[test]
fn bootstrap_backend_error_is_bound_safe_diagnostic_not_a_receipt() {
    use inframeld_cli::auth::recipient_proof::{InvalidReceipt, MaintenanceErrorCode};
    let request = BootstrapRequest::parse(&serde_json::to_vec(&request()).unwrap()).unwrap();
    let error =
        json!({"schemaVersion":1,"operationId":"original-bootstrap","code":"already_bootstrapped"});
    assert_eq!(
        request
            .validate_receipt(&serde_json::to_vec(&error).unwrap())
            .unwrap_err(),
        InvalidReceipt::Backend {
            code: MaintenanceErrorCode::AlreadyBootstrapped
        }
    );
    for invalid in [
        json!({"schemaVersion":1,"operationId":"other","code":"already_bootstrapped"}),
        json!({"schemaVersion":2,"operationId":"original-bootstrap","code":"already_bootstrapped"}),
        json!({"schemaVersion":1,"operationId":"original-bootstrap","code":"protected-upstream-sentinel"}),
        json!({"schemaVersion":1,"operationId":"original-bootstrap","code":"already_bootstrapped","detail":"protected-upstream-sentinel"}),
    ] {
        let result = request
            .validate_receipt(&serde_json::to_vec(&invalid).unwrap())
            .unwrap_err();
        assert_eq!(result, InvalidReceipt::Unavailable);
        assert!(!format!("{result:?}").contains("protected-upstream-sentinel"));
    }
}
