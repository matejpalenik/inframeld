"""Verify delivered native operations and safe application account/key schemas."""

from fastapi.testclient import TestClient

from inframeld_backend.bootstrap.application_factory import create_app


def test_native_account_contract_preserves_identity_revisions_and_safe_key_projection() -> None:
    response = TestClient(create_app()).get("/v1/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    root = "/v1/projects/{project_id}/application-accounts"
    for path, method, operation in (
        (root, "post", "createApplicationAccount"),
        (root + "/resolve", "get", "resolveApplicationAccount"),
        (root + "/{application_principal_id}", "get", "getApplicationAccount"),
        (root + "/{application_principal_id}/keys", "get", "listApplicationKeys"),
        (root + "/{application_principal_id}/keys/{key_id}", "get", "getApplicationKey"),
    ):
        entry = schema["paths"][path][method]
        assert entry["operationId"] == operation
        assert entry["security"] == [{"KratosSession": []}, {"ProductBearer": []}]
    models = schema["components"]["schemas"]
    request = models["ApplicationAccountCreationRequest"]
    assert request["additionalProperties"] is False
    revision = request["properties"]["expectedAccessRevision"]
    assert revision["type"] == "integer" and revision["format"] == "int64"
    assert type(revision["maximum"]) is int and revision["maximum"] == 9007199254740991
    for model in ("ApplicationAccountCreationResponse", "ApplicationAccountMetadataResponse"):
        bound = models[model]["properties"]["accessRevision"]
        assert type(bound["maximum"]) is int and bound["maximum"] == 9007199254740991
    created = models["ApplicationAccountCreationResponse"]["properties"]
    assert created["initialGrants"]["minItems"] == created["initialGrants"]["maxItems"] == 3
    assert "principalId" in created and "accountId" not in created
    metadata = models["ApplicationKeyMetadataResponse"]["properties"]
    assert set(metadata) == {
        "keyId",
        "applicationPrincipalId",
        "projectId",
        "prefix",
        "allowedAdapters",
        "createdAt",
        "expiresAt",
        "revokedAt",
    }
    assert metadata["prefix"]["const"] == "ifm_app_"


def test_account_sdk_fixture_preserves_native_inputs_and_independent_witness() -> None:
    from tests.support.sdk_conformance_app import create_sdk_conformance_app

    project = "00000000-0000-4000-8000-000000000003"
    with TestClient(create_sdk_conformance_app()) as client:
        client.post(
            "/sdk-control/cases/application-account-wire",
            json={"calls": {"account-create": {"kind": "none"}}},
        )
        response = client.post(
            f"/v1/projects/{project}/application-accounts",
            json={"name": "support-bot", "displayName": "SupportBot", "expectedAccessRevision": 7},
            headers={
                "Authorization": "Bearer sdk-human",
                "Idempotency-Key": "sdk-account-create",
                "X-SDK-Test": "account-create",
            },
        )
        witness = client.get("/sdk-control/cases/application-account-wire").json()
    assert response.status_code == 201
    assert response.json()["principalId"] == "00000000-0000-4000-8000-000000000008"
    assert witness["counts"] == {"account-create": 1}
    observed = witness["observations"]["account-create"]
    assert (
        observed["method"] == "POST"
        and observed["path"] == f"/v1/projects/{project}/application-accounts"
    )
    assert observed["jsonBody"] == {
        "name": "support-bot",
        "displayName": "SupportBot",
        "expectedAccessRevision": 7,
    }
