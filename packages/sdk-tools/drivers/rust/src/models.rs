#[cfg(test)]
mod tests {
    #[test]
    fn revision_models_round_trip_json_safe_maximum_without_narrowing_the_storage_type() {
        use inframeld_sdk::types::{
            HumanAdmissionRequest, MyOrganizationAccessResponse, ProjectCreationRequest,
            ProjectMembershipRequest, ProjectMetadataUpdateRequest,
        };

        fn check<Model: serde::de::DeserializeOwned + serde::Serialize>(
            input: serde_json::Value,
            field: &str,
        ) {
            for revision in [0, 9_007_199_254_740_991_i64] {
                let mut source = input.clone();
                source[field] = serde_json::json!(revision);
                let model: Model = serde_json::from_value(source.clone()).unwrap();
                assert_eq!(serde_json::to_value(model).unwrap(), source);
            }
            let mut overflow = input;
            overflow[field] = serde_json::json!(i64::MAX as u64 + 1);
            assert!(serde_json::from_value::<Model>(overflow).is_err());
        }

        let identifier = "00000000-0000-4000-8000-000000000001";
        check::<HumanAdmissionRequest>(
            serde_json::json!({"identityId": identifier}),
            "expectedAccessRevision",
        );
        check::<ProjectCreationRequest>(
            serde_json::json!({"organizationId": identifier, "name": "support", "displayName": "Support"}),
            "expectedAccessRevision",
        );
        check::<ProjectMembershipRequest>(serde_json::json!({}), "expectedAccessRevision");
        check::<ProjectMetadataUpdateRequest>(
            serde_json::json!({"name": "support"}),
            "expectedMetadataRevision",
        );
        check::<MyOrganizationAccessResponse>(
            serde_json::json!({"organizationId": identifier, "principalId": identifier, "grants": []}),
            "accessRevision",
        );
    }

    #[test]
    fn metadata_selector_change_preserves_omission_and_unicode_without_label_normalization() {
        use inframeld_sdk::types::ProjectMetadataUpdateRequest;
        let input = serde_json::json!({"expectedMetadataRevision": 0, "name": "production"});
        let value: ProjectMetadataUpdateRequest = serde_json::from_value(input.clone()).unwrap();
        assert_eq!(serde_json::to_value(value).unwrap(), input);
        for field in ["name", "displayName"] {
            let mut invalid = input.clone();
            invalid[field] = serde_json::Value::Null;
            assert!(serde_json::from_value::<ProjectMetadataUpdateRequest>(invalid).is_err());
        }
        for label in ["🧭".repeat(128), "e\u{301}".repeat(64)] {
            let input = serde_json::json!({"expectedMetadataRevision": 0, "displayName": label});
            let value: ProjectMetadataUpdateRequest =
                serde_json::from_value(input.clone()).unwrap();
            assert_eq!(serde_json::to_value(value).unwrap(), input);
        }
    }

    #[test]
    fn metadata_read_requires_nullable_selector_and_preserves_unrestricted_legacy_label() {
        use inframeld_sdk::types::ProjectMetadataResponse;
        let input = serde_json::json!({
            "projectId":"00000000-0000-4000-8000-000000000003",
            "organizationId":"00000000-0000-4000-8000-000000000002",
            "name":null, "displayName": "legacy\u{1}\n".to_string() + &"x".repeat(150),
            "metadataRevision": 0
        });
        let value: ProjectMetadataResponse = serde_json::from_value(input.clone()).unwrap();
        assert_eq!(serde_json::to_value(value).unwrap(), input);
        let mut omitted = input;
        omitted.as_object_mut().unwrap().remove("name");
        assert!(serde_json::from_value::<ProjectMetadataResponse>(omitted).is_err());
    }

    #[test]
    fn original_lookup_requires_the_guard_and_preserves_null_organization_scope() {
        let input = serde_json::json!({
            "installationId":"00000000-0000-4000-8000-000000000001",
            "organizationId":"00000000-0000-4000-8000-000000000002",
            "projectId":null,"method":"POST","requestedRoute":"/v1/original-organization-operation",
            "key":"original +/&é","expectedAuthority":{"family":"organization_action_use","actionId":"create-projects"}
        });
        let model: inframeld_sdk::types::OriginalOperationLookupRequest =
            serde_json::from_value(input.clone()).unwrap();
        assert_eq!(serde_json::to_value(model).unwrap(), input);
        let mut missing = input.clone();
        missing.as_object_mut().unwrap().remove("expectedAuthority");
        assert!(
            serde_json::from_value::<inframeld_sdk::types::OriginalOperationLookupRequest>(missing)
                .is_err()
        );
        let mut null = input;
        null["expectedAuthority"] = serde_json::Value::Null;
        assert!(
            serde_json::from_value::<inframeld_sdk::types::OriginalOperationLookupRequest>(null)
                .is_err()
        );
    }

    #[test]
    fn accepted_lookup_requires_explicit_unknown_job_and_dispatch() {
        let accepted = serde_json::json!({
            "outcome":"accepted_asynchronous","operationId":"original","admission":"confirmed",
            "jobReference":"unknown","dispatch":"not_established","idempotencyExpiresAt":null
        });
        assert!(
            serde_json::from_value::<inframeld_sdk::types::OperationLookupResponse>(
                accepted.clone()
            )
            .is_ok()
        );
        for field in [
            "outcome",
            "jobReference",
            "dispatch",
            "idempotencyExpiresAt",
        ] {
            let mut missing = accepted.clone();
            missing.as_object_mut().unwrap().remove(field);
            assert!(
                serde_json::from_value::<inframeld_sdk::types::OperationLookupResponse>(missing)
                    .is_err(),
                "accepted missing {field}"
            );
        }
        let mut invented = accepted;
        invented["jobReference"] = serde_json::json!("known");
        assert!(
            serde_json::from_value::<inframeld_sdk::types::OperationLookupResponse>(invented)
                .is_err()
        );
    }

    #[test]
    fn required_nullable_fields_cannot_be_absent() {
        let missing = serde_json::json!({"required_name":"valid", "score":0.5, "choice":7});
        assert!(
            serde_json::from_value::<inframeld_sdk_test_rust::types::ContractFixturePayload>(
                missing
            )
            .is_err()
        );
    }

    #[test]
    fn removal_acknowledgement_rejects_false_null_and_omission() {
        let grant = serde_json::json!({
            "accessRevision":1,"actionId":"create-access-groups","removed":true,"changed":true,
            "idempotencyExpiresAt":"2030-01-01T00:00:00Z","operationId":"sdk-operation",
            "projectId":"00000000-0000-4000-8000-000000000003",
            "recipientPrincipalId":"00000000-0000-4000-8000-000000000002"
        });
        assert!(
            serde_json::from_value::<inframeld_sdk::types::ProjectActionGrantRemovalResponse>(
                grant.clone()
            )
            .is_ok()
        );
        for invalid in [serde_json::json!(false), serde_json::Value::Null] {
            let mut input = grant.clone();
            input["removed"] = invalid;
            assert!(
                serde_json::from_value::<inframeld_sdk::types::ProjectActionGrantRemovalResponse>(
                    input
                )
                .is_err()
            );
        }
        let mut omitted = grant;
        omitted.as_object_mut().unwrap().remove("removed");
        assert!(
            serde_json::from_value::<inframeld_sdk::types::ProjectActionGrantRemovalResponse>(
                omitted
            )
            .is_err()
        );
    }
    use serde_json::{Value, json};
    #[test]
    fn native_problem_preserves_future_code_and_mixed_validation_path() {
        let problem: inframeld_sdk::types::ProblemDetails = serde_json::from_value(json!({"type":"about:blank","title":"Validation","status":422,"detail":"Invalid","code":"future_error_code","requestId":"00000000-0000-4000-8000-000000000099","errors":[{"location":"body","path":["items",0],"code":"invalid","message":"Invalid"}]})).unwrap();
        let observed = serde_json::to_value(problem).unwrap();
        assert_eq!(observed["errors"][0]["path"], json!(["items", 0]));
        assert_eq!(observed["code"], "future_error_code");
    }
    #[test]
    fn native_payload_keeps_omission_null_and_scalar_types() {
        let value =
            json!({"required_name":"valid","required_nullable":null,"choice":7,"score":0.5});
        let body: inframeld_sdk_test_rust::types::ContractFixturePayload =
            serde_json::from_value(value.clone()).unwrap();
        assert!(
            serde_json::to_value(body)
                .unwrap()
                .get("optional_nullable")
                .is_none()
        );
        let mut wrong = value.clone();
        wrong["choice"] = json!(true);
        assert!(
            serde_json::from_value::<inframeld_sdk_test_rust::types::ContractFixturePayload>(wrong)
                .is_err()
        );
        let mut explicit = value;
        explicit["optional_nullable"] = Value::Null;
        let body: inframeld_sdk_test_rust::types::ContractFixturePayload =
            serde_json::from_value(explicit).unwrap();
        assert_eq!(
            serde_json::to_value(body).unwrap()["optional_nullable"],
            Value::Null
        );
    }
    #[test]
    fn nullable_response_preserves_explicit_null() {
        let value = serde_json::from_str::<
            inframeld_sdk_test_rust::types::ContractFixtureNullableResponse,
        >("null");
        assert!(value.is_ok(), "nullable response rejected: {value:?}");
    }

    #[test]
    fn observed_api_error_keeps_native_bytes_instead_of_lossy_text() {
        use crate::observation::{Problem, observed};
        use crate::protocol::{Observation, WireValue, headers};
        use inframeld_sdk::client::{ApiError, ApiOpError, response::ApiResponse};
        let response: Result<ApiResponse<Value>, ApiOpError<Value>> =
            Err(ApiOpError::Api(ApiError {
                status: 200,
                headers: Default::default(),
                raw_body: vec![255, 0],
                body: "lossy rendering".into(),
                typed: None,
                parse_error: Some("decode".into()),
            }));
        let observation = observed!(response);
        let raw = observation.raw.unwrap();
        assert_eq!(raw.encoding, "base64");
        assert_eq!(raw.value, "/wA=");
        assert!(observation.error.unwrap().contains("lossy rendering"));
    }
}
