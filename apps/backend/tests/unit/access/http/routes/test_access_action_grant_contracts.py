import pytest
from fastapi.testclient import TestClient

from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@pytest.mark.parametrize("serialized", [False, True])
def test_registered_exact_grant_contracts_keep_flat_receipts_and_safe_numeric_bounds(
    serialized: bool,
) -> None:
    app = create_app()
    schema = TestClient(app).get("/v1/openapi.json").json() if serialized else app.openapi()
    models = schema["components"]["schemas"]
    for stem, base, target_fields in (
        ("Organization", "/v1/organizations/{organization_id}", {"organizationId"}),
        (
            "AccessGroup",
            "/v1/projects/{project_id}/access-groups/{access_group_id}",
            {"projectId", "accessGroupId"},
        ),
        (
            "ApplicationAccount",
            "/v1/projects/{project_id}/application-accounts/{application_principal_id}",
            {"projectId", "applicationPrincipalId"},
        ),
        ("ModelConnection", "/v1/model-connections/{model_connection_id}", {"modelConnectionId"}),
    ):
        request = models[stem + "ActionGrantRequest"]
        assert set(request["required"]) == {"canGrant", "expectedAccessRevision"}
        assert request["additionalProperties"] is False
        assert request["properties"]["canGrant"]["type"] == "boolean"
        assert "const" not in request["properties"]["canGrant"]
        for name, field in (
            (stem + "ActionGrantRequest", "expectedAccessRevision"),
            (stem + "ActionGrantResponse", "accessRevision"),
            (stem + "ActionGrantRemovalResponse", "accessRevision"),
        ):
            bound = models[name]["properties"][field]
            assert type(bound["minimum"]) is int and bound["minimum"] == 0
            assert (
                type(bound["maximum"]) is int and bound["maximum"] == RevisionValidation.MAX_VALUE
            )
        for suffix in ("Response", "RemovalResponse", "ItemResponse"):
            assert target_fields <= models[stem + "ActionGrant" + suffix]["properties"].keys()
            assert "target" not in models[stem + "ActionGrant" + suffix]["properties"]
        collection = schema["paths"][base + "/grants"]["get"]
        mutation = schema["paths"][base + "/grants/{recipient_principal_id}/{action_id}"]
        assert collection["operationId"] == "list" + stem + "ActionGrants"
        assert mutation["put"]["operationId"] == "set" + stem + "ActionGrant"
        assert {"200", "201", "413", "415"} <= mutation["put"]["responses"].keys()
        assert mutation["delete"]["operationId"] == "remove" + stem + "ActionGrant"
        assert "requestBody" not in collection and "requestBody" not in mutation["delete"]
        review = next(
            p for p in mutation["delete"]["parameters"] if p["name"] == "expectedAccessRevision"
        )
        assert review["in"] == "query" and review["required"] is True
        assert review["schema"]["maximum"] == RevisionValidation.MAX_VALUE
        for operation in (collection, mutation["put"], mutation["delete"]):
            for status in (400, 401, 403, 404, 422, 503):
                assert "application/problem+json" in operation["responses"][str(status)]["content"]

    directory = schema["paths"]["/v1/projects/{project_id}/grant-recipients"]["get"]
    assert (
        directory["operationId"] == "listProjectGrantRecipients" and "requestBody" not in directory
    )
    scalar = {p["name"]: p for p in directory["parameters"]}
    assert set(scalar) == {"project_id", "targetKind", "targetId", "actionId", "limit", "cursor"}
    assert all(scalar[name]["required"] for name in ("targetKind", "targetId", "actionId"))
    assert all(
        scalar[name]["in"] == "query"
        for name in ("targetKind", "targetId", "actionId", "limit", "cursor")
    )
    assert models["GrantTargetKind"]["enum"] == [
        "project",
        "access-group",
        "application-account",
        "model-connection",
    ]
    assert set(models["GrantRecipientResponse"]["properties"]) == {
        "principalId",
        "displayName",
        "kind",
    }


def test_retired_post_has_no_live_native_operation_or_creation_only_models() -> None:
    app = create_app()
    client = TestClient(app)
    response = client.post(
        "/v1/projects/00000000-0000-0000-0000-000000000003/grants",
        headers={"Idempotency-Key": "retained-original-post"},
        json={
            "recipientPrincipalId": "00000000-0000-0000-0000-000000000002",
            "actionId": "create-access-groups",
            "canGrant": False,
            "expectedAccessRevision": 7,
        },
    )
    assert response.status_code == 405 and response.headers["cache-control"] == "no-store"
    schema = app.openapi()
    assert "post" not in schema["paths"]["/v1/projects/{project_id}/grants"]
    assert "ProjectUseOnlyGrantRequest" not in schema["components"]["schemas"]
    assert "ProjectUseOnlyGrantResponse" not in schema["components"]["schemas"]
