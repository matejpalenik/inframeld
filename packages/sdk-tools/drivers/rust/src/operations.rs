use crate::observation::{Problem, observed};
use crate::protocol::{Call, Observation, WireValue, headers};
use inframeld_sdk::client::*;
use inframeld_sdk_test_rust::client as fixture;
use serde_json::Value;

pub async fn observe(
    client: &HttpClient,
    fixture: &fixture::HttpClient,
    request: &Call,
) -> Observation {
    let body = request.body.clone().unwrap_or(Value::Null);
    match request.operation.as_str() {
        "contractFixtureVariants" => {
            let native = fixture
                .contract_fixture_variants(
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("mode"))
                        .and_then(Value::as_str),
                )
                .await;
            let bodyless = native.as_ref().is_ok_and(|value| {
                matches!(
                    value.body,
                    fixture::ContractFixtureVariantsHttpResponseBody::Status204Representation2
                )
            });
            let mut result = observed!(native);
            if bodyless {
                result.body = None;
                result.validation = "none".into();
            }
            result
        }
        "contractFixtureFallback" => {
            let native = fixture
                .contract_fixture_fallback(
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("mode"))
                        .and_then(Value::as_str),
                )
                .await;
            let bodyless = native.as_ref().is_ok_and(|value| {
                matches!(
                    value.body,
                    fixture::ContractFixtureFallbackHttpResponseBody::Status204Representation0
                )
            });
            let mut result = observed!(native);
            if bodyless {
                result.body = None;
                result.validation = "none".into();
            }
            result
        }
        "contractFixtureMedia" => observed!(fixture.contract_fixture_media().await),
        "getProtectedResourceMetadata" => observed!(client.get_protected_resource_metadata().await),
        "getProtectedResourceMetadataForPath" => observed!(
            client
                .get_protected_resource_metadata_for_path(
                    request.path.as_ref().unwrap()["resource_path"]
                        .as_str()
                        .unwrap()
                )
                .await
        ),
        "getHealth" => observed!(client.get_health().await),
        "getCurrentSession" => observed!(client.get_current_session().await),
        "inspectHumanOAuthConsent" => observed!(
            client
                .inspect_human_o_auth_consent(
                    request.query.as_ref().unwrap()["consent_challenge"]
                        .as_str()
                        .unwrap()
                )
                .await
        ),
        "decideHumanOAuthConsent" => observed!(
            client
                .decide_human_o_auth_consent(serde_json::from_value(body).unwrap())
                .await
        ),
        "lookupOriginalOperation" => observed!(
            client
                .lookup_original_operation(serde_json::from_value(body).unwrap())
                .await
        ),
        "assignProjectUseOnlyGrant" => observed!(
            client
                .assign_project_use_only_grant(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "contractFixtureNullable" => observed!(fixture.contract_fixture_nullable().await),
        "contractFixtureEmpty" => {
            let mut result = observed!(fixture.contract_fixture_empty().await);
            if result.kind == "success" {
                result.body = None;
                result.validation = "none".into();
            }
            result
        }
        "contractFixturePayload" => observed!(
            fixture
                .contract_fixture_payload(serde_json::from_value(body).unwrap())
                .await
        ),
        "contractFixturePage" => {
            let query = request.query.as_ref();
            observed!(
                fixture
                    .contract_fixture_page(
                        query.and_then(|v| v["limit"].as_i64()),
                        query.and_then(|v| v["cursor"].as_str())
                    )
                    .await
            )
        }
        "contractFixtureUpload" => {
            use base64::Engine;
            let bytes = base64::engine::general_purpose::STANDARD
                .decode(body["fileBase64"].as_str().unwrap())
                .unwrap();
            let file = inframeld_sdk_test_rust::types::MultipartFile::from(bytes)
                .with_file_name(body["fileName"].as_str().unwrap())
                .with_content_type("application/octet-stream");
            observed!(
                fixture
                    .contract_fixture_upload(
                        inframeld_sdk_test_rust::types::BodyContractFixtureUpload {
                            file,
                            label: body["label"].as_str().unwrap().into()
                        }
                    )
                    .await
            )
        }
        _ => panic!("Unsupported operation {}", request.operation),
    }
}
