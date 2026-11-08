"""Verify the registered public invitation contract independently of exported artifacts."""

import pytest

from inframeld_backend.bootstrap.application_factory import create_app


@pytest.mark.parametrize(
    "path,operation_id,response,status,recipient",
    [
        ("/v1/invitations", "issueInvitation", "InvitationIssueResponse", "201", False),
        (
            "/v1/invitations/{invitation_id}/revoke",
            "revokeInvitation",
            "InvitationRevocationResponse",
            "200",
            False,
        ),
        ("/v1/invitations/preview", "previewInvitation", "InvitationPreviewResponse", "200", True),
        (
            "/v1/invitations/activate",
            "activateInvitation",
            "InvitationActivationResponse",
            "200",
            True,
        ),
    ],
)
def test_native_invitation_operations_publish_exact_authentication_and_outcomes(
    path: str, operation_id: str, response: str, status: str, recipient: bool
) -> None:
    schema = create_app().openapi()
    assert path in schema["paths"]
    operation = schema["paths"][path]["post"]
    assert operation["operationId"] == operation_id
    assert operation["security"] == (
        [{"KratosSession": []}] if recipient else [{"KratosSession": []}, {"ProductBearer": []}]
    )
    assert operation["responses"][status]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/" + response
    }
    for error_status in ("400", "401", "403", "404", "409", "413", "415", "422", "503"):
        assert "application/problem+json" in operation["responses"][error_status]["content"]
    keys = [
        item
        for item in operation.get("parameters", [])
        if item["name"] == "Idempotency-Key" and item["in"] == "header"
    ]
    assert bool(keys) is (operation_id != "previewInvitation")
    if keys:
        assert len(keys) == 1 and keys[0]["required"] is True
    assert not any(item["in"] == "query" for item in operation.get("parameters", []))


def test_native_issuance_union_omits_secret_from_replay_and_keeps_strict_input() -> None:
    components = create_app().openapi()["components"]["schemas"]
    assert "InvitationIssueResponse" in components
    response = components["InvitationIssueResponse"]
    assert response["discriminator"]["propertyName"] == "secretAvailable"
    assert {item["$ref"] for item in response["oneOf"]} == {
        "#/components/schemas/InvitationFirstDeliveryResponse",
        "#/components/schemas/InvitationIssuanceReplayResponse",
    }
    first, replay = (
        components["InvitationFirstDeliveryResponse"],
        components["InvitationIssuanceReplayResponse"],
    )
    assert "invitationToken" in first["required"]
    assert "invitationToken" not in replay["properties"]
    assert first["properties"]["secretAvailable"]["const"] is True
    assert replay["properties"]["secretAvailable"]["const"] is False
    issue = components["InvitationIssueRequest"]
    assert issue["additionalProperties"] is False
    assert issue["properties"]["assignments"]["minItems"] == 1
    assert issue["properties"]["assignments"]["maxItems"] == 100
    lifetime = issue["properties"]["expiresInSeconds"]
    assert lifetime["type"] == "integer" and lifetime["maximum"] == 2592000
    assert "expiresInSeconds" not in issue["required"]
    for request in ("InvitationPreviewRequest", "InvitationActivationRequest"):
        assert set(components[request]["required"]) == {"invitationToken"}
        assert set(components[request]["properties"]) == {"invitationToken"}
        assert components[request]["additionalProperties"] is False
