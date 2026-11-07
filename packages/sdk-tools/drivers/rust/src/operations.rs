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
        "listOrganizationActionGrants" => observed!(
            client
                .list_organization_action_grants(
                    request.path.as_ref().unwrap()["organization_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["actionId"]
                        .as_str()
                        .unwrap(),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("limit"))
                        .and_then(Value::as_i64),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("cursor"))
                        .and_then(Value::as_str)
                )
                .await
        ),
        "setOrganizationActionGrant" => observed!(
            client
                .set_organization_action_grant(
                    request.path.as_ref().unwrap()["organization_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["recipient_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["action_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "removeOrganizationActionGrant" => observed!(
            client
                .remove_organization_action_grant(
                    request.path.as_ref().unwrap()["organization_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["recipient_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["action_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["expectedAccessRevision"]
                        .as_i64()
                        .unwrap(),
                    &request.headers["Idempotency-Key"]
                )
                .await
        ),
        "listAccessGroupActionGrants" => observed!(
            client
                .list_access_group_action_grants(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["actionId"]
                        .as_str()
                        .unwrap(),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("limit"))
                        .and_then(Value::as_i64),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("cursor"))
                        .and_then(Value::as_str)
                )
                .await
        ),
        "setAccessGroupActionGrant" => observed!(
            client
                .set_access_group_action_grant(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["recipient_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["action_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "removeAccessGroupActionGrant" => observed!(
            client
                .remove_access_group_action_grant(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["recipient_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["action_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["expectedAccessRevision"]
                        .as_i64()
                        .unwrap(),
                    &request.headers["Idempotency-Key"]
                )
                .await
        ),
        "listApplicationAccountActionGrants" => observed!(
            client
                .list_application_account_action_grants(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["application_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["actionId"]
                        .as_str()
                        .unwrap(),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("limit"))
                        .and_then(Value::as_i64),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("cursor"))
                        .and_then(Value::as_str)
                )
                .await
        ),
        "setApplicationAccountActionGrant" => observed!(
            client
                .set_application_account_action_grant(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["application_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["recipient_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["action_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "removeApplicationAccountActionGrant" => observed!(
            client
                .remove_application_account_action_grant(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["application_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["recipient_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["action_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["expectedAccessRevision"]
                        .as_i64()
                        .unwrap(),
                    &request.headers["Idempotency-Key"]
                )
                .await
        ),
        "listProjectGrantRecipients" => observed!(
            client
                .list_project_grant_recipients(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    serde_json::from_value(request.query.as_ref().unwrap()["targetKind"].clone())
                        .unwrap(),
                    request.query.as_ref().unwrap()["targetId"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["actionId"]
                        .as_str()
                        .unwrap(),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("limit"))
                        .and_then(Value::as_i64),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("cursor"))
                        .and_then(Value::as_str)
                )
                .await
        ),
        "getMyProjectAccess" => observed!(
            client
                .get_my_project_access(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("limit"))
                        .and_then(Value::as_i64),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("cursor"))
                        .and_then(Value::as_str)
                )
                .await
        ),
        "setProjectActionGrant" => observed!(
            client
                .set_project_action_grant(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["recipient_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["action_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "removeProjectActionGrant" => observed!(
            client
                .remove_project_action_grant(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["recipient_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["action_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["expectedAccessRevision"]
                        .as_i64()
                        .unwrap(),
                    &request.headers["Idempotency-Key"]
                )
                .await
        ),
        "addProjectMember" => observed!(
            client
                .add_project_member(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["principal_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "removeProjectMember" => observed!(
            client
                .remove_project_member(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["principal_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["expectedAccessRevision"]
                        .as_i64()
                        .unwrap(),
                    &request.headers["Idempotency-Key"]
                )
                .await
        ),
        "admitHuman" => observed!(
            client
                .admit_human(
                    request.path.as_ref().unwrap()["organization_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
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
        "resolveProjectName" => observed!(
            client
                .resolve_project_name(request.path.as_ref().unwrap()["name"].as_str().unwrap())
                .await
        ),
        "getProjectMetadata" => observed!(
            client
                .get_project_metadata(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap()
                )
                .await
        ),
        "updateProjectMetadata" => observed!(
            client
                .update_project_metadata(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "getCurrentSession" => observed!(client.get_current_session().await),
        "getCurrentApplicationSession" => observed!(client.get_current_application_session().await),
        "getMyOrganizationAccess" => observed!(client.get_my_organization_access().await),
        "listProjectMembers" => {
            let query = request.query.as_ref();
            observed!(
                client
                    .list_project_members(
                        request.path.as_ref().unwrap()["project_id"]
                            .as_str()
                            .unwrap(),
                        query.and_then(|value| value["limit"].as_i64()),
                        query.and_then(|value| value["cursor"].as_str())
                    )
                    .await
            )
        }
        "listProjectActionGrants" => {
            let query = request.query.as_ref().unwrap();
            observed!(
                client
                    .list_project_action_grants(
                        request.path.as_ref().unwrap()["project_id"]
                            .as_str()
                            .unwrap(),
                        query["actionId"].as_str().unwrap(),
                        query["limit"].as_i64(),
                        query["cursor"].as_str()
                    )
                    .await
            )
        }
        "createAccessGroup" => observed!(
            client
                .create_access_group(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "getAccessGroup" => observed!(
            client
                .get_access_group(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap()
                )
                .await
        ),
        "resolveAccessGroup" => observed!(
            client
                .resolve_access_group(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["name"].as_str().unwrap()
                )
                .await
        ),
        "listAccessGroupMembers" => observed!(
            client
                .list_access_group_members(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("limit"))
                        .and_then(Value::as_i64),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("cursor"))
                        .and_then(Value::as_str)
                )
                .await
        ),
        "listAccessGroupManagers" => observed!(
            client
                .list_access_group_managers(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("limit"))
                        .and_then(Value::as_i64),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("cursor"))
                        .and_then(Value::as_str)
                )
                .await
        ),
        "addAccessGroupMember" => observed!(
            client
                .add_access_group_member(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["principal_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "removeAccessGroupMember" => observed!(
            client
                .remove_access_group_member(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["principal_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["expectedAccessRevision"]
                        .as_i64()
                        .unwrap(),
                    &request.headers["Idempotency-Key"]
                )
                .await
        ),
        "appointAccessGroupManager" => observed!(
            client
                .appoint_access_group_manager(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["principal_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "removeAccessGroupManager" => observed!(
            client
                .remove_access_group_manager(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["principal_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["expectedAccessRevision"]
                        .as_i64()
                        .unwrap(),
                    &request.headers["Idempotency-Key"]
                )
                .await
        ),
        "deleteAccessGroup" => observed!(
            client
                .delete_access_group(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["access_group_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["expectedAccessRevision"]
                        .as_i64()
                        .unwrap(),
                    &request.headers["Idempotency-Key"]
                )
                .await
        ),
        "createApplicationAccount" => observed!(
            client
                .create_application_account(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
        "getApplicationAccount" => observed!(
            client
                .get_application_account(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["application_principal_id"]
                        .as_str()
                        .unwrap()
                )
                .await
        ),
        "resolveApplicationAccount" => observed!(
            client
                .resolve_application_account(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.query.as_ref().unwrap()["name"].as_str().unwrap()
                )
                .await
        ),
        "listApplicationKeys" => observed!(
            client
                .list_application_keys(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["application_principal_id"]
                        .as_str()
                        .unwrap(),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("limit"))
                        .and_then(Value::as_i64),
                    request
                        .query
                        .as_ref()
                        .and_then(|query| query.get("cursor"))
                        .and_then(Value::as_str)
                )
                .await
        ),
        "getApplicationKey" => observed!(
            client
                .get_application_key(
                    request.path.as_ref().unwrap()["project_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["application_principal_id"]
                        .as_str()
                        .unwrap(),
                    request.path.as_ref().unwrap()["key_id"].as_str().unwrap()
                )
                .await
        ),
        "createProject" => observed!(
            client
                .create_project(
                    &request.headers["Idempotency-Key"],
                    serde_json::from_value(body).unwrap()
                )
                .await
        ),
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
        "getDeletionStatus" => observed!(
            client
                .get_deletion_status(
                    request.query.as_ref().unwrap()["operationId"]
                        .as_str()
                        .unwrap()
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
