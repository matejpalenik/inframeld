#[cfg(test)]
mod tests {
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
    fn boolean_constants_reject_true_and_explicit_null() {
        let grant = serde_json::json!({
            "accessRevision":1,"actionId":"create-access-groups","canGrant":false,
            "idempotencyExpiresAt":"2030-01-01T00:00:00Z","operationId":"sdk-operation",
            "projectId":"00000000-0000-4000-8000-000000000003",
            "recipientPrincipalId":"00000000-0000-4000-8000-000000000002"
        });
        assert!(
            serde_json::from_value::<inframeld_sdk::types::ProjectUseOnlyGrantResponse>(
                grant.clone()
            )
            .is_ok()
        );
        for invalid in [serde_json::json!(true), serde_json::Value::Null] {
            let mut input = grant.clone();
            input["canGrant"] = invalid;
            assert!(
                serde_json::from_value::<inframeld_sdk::types::ProjectUseOnlyGrantResponse>(input)
                    .is_err()
            );
        }
        let mut omitted = grant;
        omitted.as_object_mut().unwrap().remove("canGrant");
        assert!(
            serde_json::from_value::<inframeld_sdk::types::ProjectUseOnlyGrantResponse>(omitted)
                .is_ok()
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
