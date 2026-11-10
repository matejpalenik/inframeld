"""Verify committed OpenAPI output and generated HTTP schema conventions."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from pydantic import BaseModel, ValidationError
from tests.support.openapi_schema_fixture import create_schema_fixture_app

from inframeld_backend.access.http.requests.human_admission_request import HumanAdmissionRequest
from inframeld_backend.access.http.requests.project_creation_request import ProjectCreationRequest
from inframeld_backend.access.http.requests.project_membership_request import (
    ProjectMembershipRequest,
)
from inframeld_backend.access.http.requests.project_metadata_update_request import (
    ProjectMetadataUpdateRequest,
)
from inframeld_backend.bootstrap.application_factory import create_app

CONTRACT_PATH = (
    Path(__file__).resolve().parents[5] / "contracts" / "openapi" / "v1" / "inframeld-v1.json"
)


@pytest.mark.parametrize("public_json", [False, True], ids=["native", "public-json"])
@pytest.mark.parametrize(
    ("component", "field"),
    [
        ("HumanAdmissionRequest", "expectedAccessRevision"),
        ("ProjectCreationRequest", "expectedAccessRevision"),
        ("ProjectMembershipRequest", "expectedAccessRevision"),
        ("ProjectMetadataUpdateRequest", "expectedMetadataRevision"),
        ("MyOrganizationAccessResponse", "accessRevision"),
    ],
)
def test_native_and_public_schemas_preserve_exact_integer_revision_bounds(
    component: str, field: str, public_json: bool
) -> None:
    application = create_app()
    if public_json:
        response = TestClient(application).get("/v1/openapi.json")
        assert response.status_code == 200
        schema = response.json()
    else:
        schema = application.openapi()

    revision = schema["components"]["schemas"][component]["properties"][field]
    assert revision["type"] == "integer"
    assert revision["format"] == "int64"
    assert type(revision["minimum"]) is int and revision["minimum"] == 0
    assert type(revision["maximum"]) is int and revision["maximum"] == 2**53 - 1


@pytest.mark.parametrize(
    ("model", "field", "other_fields"),
    [
        (
            HumanAdmissionRequest,
            "expectedAccessRevision",
            {"identityId": "00000000-0000-4000-8000-000000000001"},
        ),
        (
            ProjectCreationRequest,
            "expectedAccessRevision",
            {
                "organizationId": "00000000-0000-4000-8000-000000000001",
                "name": "support",
                "displayName": "Support",
            },
        ),
        (ProjectMembershipRequest, "expectedAccessRevision", {}),
        (ProjectMetadataUpdateRequest, "expectedMetadataRevision", {"name": "support"}),
    ],
)
def test_request_revision_models_accept_exact_maximum_and_reject_its_successor(
    model: type[BaseModel], field: str, other_fields: dict[str, object]
) -> None:
    for revision in (0, 2**53 - 1):
        request = model.model_validate({**other_fields, field: revision})
        assert request.model_dump(by_alias=True)[field] == revision

    with pytest.raises(ValidationError):
        model.model_validate({**other_fields, field: 2**53})


def test_human_admission_contract_preserves_original_receipt_and_current_human_scope() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/v1/organizations/{organization_id}/human-admissions"]["post"]
    assert operation["operationId"] == "admitHuman"
    assert operation["security"] == [{"KratosSession": []}, {"ProductBearer": []}]
    for status in ("200", "201"):
        assert operation["responses"][status]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/HumanAdmissionResponse"
        }
    for status in ("400", "401", "403", "404", "409", "413", "415", "422", "503"):
        assert "application/problem+json" in operation["responses"][status]["content"]
    assert any(
        item["name"] == "organization_id" and item["in"] == "path" and item["required"]
        for item in operation["parameters"]
    )
    assert any(
        item["name"] == "Idempotency-Key" and item["in"] == "header"
        for item in operation["parameters"]
    )
    request = schema["components"]["schemas"]["HumanAdmissionRequest"]
    assert request["additionalProperties"] is False
    assert set(request["required"]) == {"identityId", "expectedAccessRevision"}
    assert request["properties"]["identityId"]["format"] == "uuid"
    assert request["properties"]["expectedAccessRevision"]["minimum"] == 0
    assert request["properties"]["expectedAccessRevision"]["maximum"] == 2**53 - 1
    response = schema["components"]["schemas"]["HumanAdmissionResponse"]
    assert set(response["required"]) == {
        "operationId",
        "idempotencyExpiresAt",
        "organizationId",
        "principalId",
        "accessRevision",
        "changed",
    }
    assert response["properties"]["idempotencyExpiresAt"]["type"] == "string"
    assert response["properties"]["idempotencyExpiresAt"]["format"] == "date-time"


def test_openapi_contract_matches_application() -> None:
    """Prove the committed OpenAPI document matches the current application."""

    assert CONTRACT_PATH.exists(), (
        "The OpenAPI contract is missing. Run `pnpm openapi` to generate it."
    )

    committed_contract = cast(dict[str, Any], json.loads(CONTRACT_PATH.read_text(encoding="utf-8")))

    generated_contract = create_app().openapi()

    assert committed_contract == generated_contract, (
        "The OpenAPI contract is stale. Run `pnpm openapi` to regenerate it."
    )

    assert generated_contract["openapi"].startswith("3.1."), (
        "The application must emit native OpenAPI 3.1.x."
    )
    operation_ids: list[str | None] = []

    for path_item in generated_contract["paths"].values():
        for operation in path_item.values():
            if not isinstance(operation, dict) or "responses" not in operation:
                continue

            typed_operation = cast(dict[str, Any], operation)
            operation_ids.append(cast(str | None, typed_operation.get("operationId")))

    assert all(isinstance(operation_id, str) and operation_id for operation_id in operation_ids), (
        "Every public operation must define an operationId."
    )
    assert len(operation_ids) == len(set(operation_ids)), "Public operationIds must be unique."


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/v1/session", "get"),
        (
            "/v1/projects/{project_id}/grants/{recipient_principal_id}/{action_id}",
            "put",
        ),
        ("/v1/organizations/{organization_id}/grants", "get"),
        (
            "/v1/organizations/{organization_id}/grants/{recipient_principal_id}/{action_id}",
            "put",
        ),
        (
            "/v1/organizations/{organization_id}/grants/{recipient_principal_id}/{action_id}",
            "delete",
        ),
        ("/v1/projects/{project_id}/access-groups/{access_group_id}/grants", "get"),
        (
            "/v1/projects/{project_id}/access-groups/{access_group_id}/grants/{recipient_principal_id}/{action_id}",
            "put",
        ),
        (
            "/v1/projects/{project_id}/access-groups/{access_group_id}/grants/{recipient_principal_id}/{action_id}",
            "delete",
        ),
        (
            "/v1/projects/{project_id}/application-accounts/{application_principal_id}/grants",
            "get",
        ),
        (
            "/v1/projects/{project_id}/application-accounts/{application_principal_id}/grants/{recipient_principal_id}/{action_id}",
            "put",
        ),
        (
            "/v1/projects/{project_id}/application-accounts/{application_principal_id}/grants/{recipient_principal_id}/{action_id}",
            "delete",
        ),
        ("/v1/projects/{project_id}/grant-recipients", "get"),
        ("/v1/operations/lookup", "post"),
        ("/v1/projects/{project_id}/metadata", "get"),
        ("/v1/projects/{project_id}/members", "get"),
        ("/v1/projects/{project_id}/metadata", "patch"),
        ("/v1/projects/by-name/{name}", "get"),
    ],
)
def test_identity_and_product_routes_declare_their_bearer_family_and_authentication_errors(
    path: str, method: str
) -> None:
    """Keep the human identity route exclusive while ordinary routes dispatch product bearers."""
    schema = create_app().openapi()
    operation = schema["paths"][path][method]

    bearer = "HumanBearer" if path == "/v1/session" else "ProductBearer"
    assert operation["security"] == [
        {"KratosSession": []},
        {bearer: []},
    ]
    schemes = schema["components"]["securitySchemes"]
    assert schemes["KratosSession"]["type"] == "apiKey"
    assert schemes["KratosSession"]["in"] == "cookie"
    assert schemes["KratosSession"]["name"] == "ory_kratos_session"
    assert schemes[bearer]["type"] == "http"
    assert schemes[bearer]["scheme"] == "bearer"

    for status in ("400", "401"):
        response = operation["responses"][status]
        assert set(response["content"]) == {"application/problem+json"}
        assert response["content"]["application/problem+json"]["schema"] == {
            "$ref": "#/components/schemas/ProblemDetails"
        }
        assert response["headers"]["WWW-Authenticate"]["schema"] == {"type": "string"}

    if path == "/v1/session":
        assert operation["operationId"] == "getCurrentSession"
        assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
            "$ref": "#/components/schemas/CurrentSessionResponse"
        }


def test_schema_fixture_preserves_native_field_semantics() -> None:
    """Prove native OpenAPI preserves required, nullable, union and field constraints."""

    schema = create_schema_fixture_app().openapi()
    payload_schema = schema["components"]["schemas"]["ContractFixturePayload"]
    properties = payload_schema["properties"]

    assert set(payload_schema["required"]) == {
        "required_name",
        "required_nullable",
        "score",
        "choice",
    }
    assert "optional_nullable" not in payload_schema["required"]

    assert properties["required_name"]["minLength"] == 1
    assert properties["required_name"]["maxLength"] == 40
    assert properties["required_name"]["pattern"] == "^[a-z]+$"

    assert properties["score"]["minimum"] == 0
    assert properties["score"]["maximum"] == 1

    assert {item["type"] for item in properties["required_nullable"]["anyOf"]} == {
        "string",
        "null",
    }
    assert {item["type"] for item in properties["choice"]["anyOf"]} == {
        "string",
        "integer",
    }


def test_project_members_native_contract_is_one_bounded_page_with_explicit_continuation() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/v1/projects/{project_id}/members"]["get"]
    assert operation["operationId"] == "listProjectMembers"
    assert "requestBody" not in operation
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
    assert set(parameters) == {"project_id", "limit", "cursor"}
    assert parameters["project_id"]["schema"]["format"] == "uuid"
    limit = parameters["limit"]["schema"]
    assert (limit["default"], limit["minimum"], limit["maximum"]) == (25, 1, 100)
    cursor = parameters["cursor"]["schema"]["anyOf"][0]
    assert (cursor["minLength"], cursor["maxLength"]) == (1, 1024)
    page = schema["components"]["schemas"]["ProjectMembersPageResponse"]
    assert set(page["required"]) == {"projectId", "accessRevision", "items", "nextCursor"}
    assert set(page["properties"]) == set(page["required"])
    assert {choice["type"] for choice in page["properties"]["nextCursor"]["anyOf"]} == {
        "string",
        "null",
    }
    member = schema["components"]["schemas"]["ProjectMemberResponse"]
    assert set(member["required"]) == {"principalId", "displayName", "kind"}
    assert set(member["properties"]) == set(member["required"])
    for status in ("401", "403", "404", "422", "503"):
        assert set(operation["responses"][status]["content"]) == {"application/problem+json"}


def test_schema_fixture_preserves_multipart_uploads() -> None:
    """Prove native OpenAPI describes multipart files and constrained form fields."""

    schema = create_schema_fixture_app().openapi()
    request_body = schema["paths"]["/contract-fixture/upload"]["post"]["requestBody"]

    assert set(request_body["content"]) == {"multipart/form-data"}

    multipart_schema = request_body["content"]["multipart/form-data"]["schema"]

    if "$ref" in multipart_schema:
        component_name = multipart_schema["$ref"].rsplit("/", maxsplit=1)[-1]
        multipart_schema = schema["components"]["schemas"][component_name]

    assert set(multipart_schema["required"]) == {"file", "label"}
    file_schema = multipart_schema["properties"]["file"]

    assert file_schema["type"] == "string"
    assert file_schema["contentMediaType"] == "application/octet-stream"
    assert multipart_schema["properties"]["label"]["minLength"] == 1
    assert multipart_schema["properties"]["label"]["maxLength"] == 20


def test_validation_error_media_type_matches_openapi() -> None:
    """Ensure clients are told the actual media type of validation errors."""
    application = create_schema_fixture_app()

    with TestClient(application) as client:
        response = client.post("/contract-fixture/payload", json={})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"

    schema = application.openapi()
    documented_response = schema["paths"]["/contract-fixture/payload"]["post"]["responses"]["422"]

    assert set(documented_response["content"]) == {"application/problem+json"}

    problem_schema = documented_response["content"]["application/problem+json"]["schema"]
    assert problem_schema == {"$ref": "#/components/schemas/ProblemDetails"}

    components = schema["components"]["schemas"]
    assert "ProblemDetails" in components
    assert "ValidationIssue" in components

    success_response = schema["paths"]["/contract-fixture/payload"]["post"]["responses"]["200"]
    assert set(success_response["content"]) == {"application/json"}


def test_upload_validation_error_matches_openapi() -> None:
    """Document the problem returned when an upload omits a required form field."""
    application = create_schema_fixture_app()

    with TestClient(application) as client:
        response = client.post(
            "/contract-fixture/upload",
            files={"file": ("example.txt", b"example", "text/plain")},
        )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"

    schema = application.openapi()
    documented_response = schema["paths"]["/contract-fixture/upload"]["post"]["responses"]["422"]

    assert set(documented_response["content"]) == {"application/problem+json"}
    assert documented_response["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/ProblemDetails"
    }


def test_problem_components_preserve_wire_contract() -> None:
    """Preserve public field names, optionality, limits, and descriptions."""
    schema = create_schema_fixture_app().openapi()
    components = schema["components"]["schemas"]

    problem = components["ProblemDetails"]
    properties = problem["properties"]

    assert set(problem["required"]) == {
        "type",
        "title",
        "status",
        "detail",
        "code",
        "requestId",
    }
    assert "request_id" not in properties
    assert properties["requestId"]["format"] == "uuid"
    assert properties["status"]["minimum"] == 400
    assert properties["status"]["maximum"] == 599

    # The model allows absent/null errors; the response builder omits None.
    error_variants = properties["errors"]["anyOf"]
    assert any(variant.get("type") == "null" for variant in error_variants)

    error_array = next(variant for variant in error_variants if variant.get("type") == "array")
    assert error_array["maxItems"] == 20
    assert error_array["items"] == {"$ref": "#/components/schemas/ValidationIssue"}

    issue = components["ValidationIssue"]
    assert set(issue["required"]) == {"location", "path", "code", "message"}
    assert issue["properties"]["path"]["maxItems"] == 8
    assert issue["properties"]["message"]["maxLength"] == 256

    for component in (problem, issue):
        for field in component["properties"].values():
            assert field.get("description"), "Public fields need useful descriptions."


def test_health_contract_declares_internal_error() -> None:
    """Describe unexpected health-request failures using the shared problem model."""
    schema = create_app().openapi()
    responses = schema["paths"]["/health"]["get"]["responses"]

    assert "500" in responses
    assert set(responses["200"]["content"]) == {"application/json"}
    assert set(responses["500"]["content"]) == {"application/problem+json"}
    assert responses["500"]["content"]["application/problem+json"]["schema"] == {
        "$ref": "#/components/schemas/ProblemDetails"
    }
    assert "ProblemDetails" in schema["components"]["schemas"]


def test_production_contract_excludes_fixture_routes() -> None:
    """Keep synthetic contract-test endpoints out of the published API."""
    schema = create_app().openapi()

    assert not any(path.startswith("/contract-fixture/") for path in schema["paths"])


def test_pagination_fixture_preserves_query_and_response_contract() -> None:
    """Publish bounded query parameters and the camel-case page response."""
    schema = create_schema_fixture_app().openapi()
    operation = schema["paths"]["/contract-fixture/page"]["get"]

    parameters = {parameter["name"]: parameter["schema"] for parameter in operation["parameters"]}
    assert set(parameters) == {"limit", "cursor"}
    assert parameters["limit"]["default"] == 25
    assert parameters["limit"]["minimum"] == 1
    assert parameters["limit"]["maximum"] == 100

    cursor_string = next(
        variant for variant in parameters["cursor"]["anyOf"] if variant.get("type") == "string"
    )
    assert cursor_string["minLength"] == 1
    assert cursor_string["maxLength"] == 1024
    assert cursor_string["pattern"] == "^[A-Za-z0-9_-]+$"

    response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    component_name = response_schema["$ref"].rsplit("/", maxsplit=1)[-1]
    page_schema = schema["components"]["schemas"][component_name]

    assert set(page_schema["required"]) == {"items", "nextCursor"}
    assert page_schema["properties"]["items"]["items"]["type"] == "integer"
    assert "next_cursor" not in page_schema["properties"]
    assert any(
        variant.get("type") == "null"
        for variant in page_schema["properties"]["nextCursor"]["anyOf"]
    )
    assert set(operation["responses"]["422"]["content"]) == {"application/problem+json"}


@pytest.mark.parametrize(
    "method,operation_id",
    [("get", "inspectHumanOAuthConsent"), ("post", "decideHumanOAuthConsent")],
)
def test_consent_declares_cookie_only_security_and_problem_responses(
    method: str, operation_id: str
) -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/v1/oauth/consent"][method]
    assert operation["operationId"] == operation_id
    assert operation["security"] == [{"KratosSession": []}]
    for status in ("400", "401", "403", "404", "422", "503"):
        assert set(operation["responses"][status]["content"]) == {"application/problem+json"}
    if method == "post":
        request = schema["components"]["schemas"]["HumanOAuthConsentRequest"]
        assert request["additionalProperties"] is False
        assert set(request["properties"]) == {"consentChallenge", "decision", "remember"}


@pytest.mark.parametrize(
    "model,required",
    [
        ("CompletedOperationLookupResponse", {"outcome"}),
        (
            "AcceptedOperationLookupResponse",
            {"outcome", "admission", "jobReference", "dispatch", "idempotencyExpiresAt"},
        ),
        ("InProgressOperationLookupResponse", {"outcome"}),
        ("RecoveryRequiredOperationLookupResponse", {"outcome", "reason"}),
        ("UnresolvedOperationLookupResponse", {"outcome"}),
    ],
)
def test_lookup_wire_alternatives_require_their_discriminator_and_uncertainty(
    model: str, required: set[str]
) -> None:
    """Clients must reject absent outcome tags and absent explicit uncertainty fields."""
    schema = create_app().openapi()["components"]["schemas"][model]
    assert required <= set(schema.get("required", []))


def test_deletion_status_contract_preserves_human_read_and_explicit_unknowns() -> None:
    """Give generated clients the registered, content-free read and required nullable facts."""
    schema = create_app().openapi()
    assert "/v1/deletions/status" in schema["paths"]
    operation = schema["paths"]["/v1/deletions/status"]["get"]
    assert operation["operationId"] == "getDeletionStatus"
    assert operation["security"] == [{"KratosSession": []}, {"ProductBearer": []}]
    assert "requestBody" not in operation
    assert len(operation["parameters"]) == 1
    parameter = operation["parameters"][0]
    assert parameter["name"] == "operationId"
    assert parameter["in"] == "query" and parameter["required"] is True
    assert parameter["schema"]["minLength"] == 1
    assert parameter["schema"]["maxLength"] == 128

    components = schema["components"]["schemas"]
    success = operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert success == {"$ref": "#/components/schemas/DeletionStatusResponse"}
    alternatives = components["DeletionStatusResponse"]
    assert alternatives["discriminator"] == {
        "propertyName": "outcome",
        "mapping": {
            "retained": "#/components/schemas/RetainedDeletionStatusResponse",
            "unresolved": "#/components/schemas/UnresolvedDeletionStatusResponse",
        },
    }
    retained = components["RetainedDeletionStatusResponse"]
    assert retained["additionalProperties"] is False
    fields = {
        "outcome",
        "operationId",
        "jobState",
        "admissionConfirmed",
        "accessBlocked",
        "applicationShutdownComplete",
        "physicalCleanupComplete",
        "retentionExpiresAt",
    }
    assert set(retained["required"]) == set(retained["properties"]) == fields
    for name in fields - {"outcome", "operationId"}:
        assert any(part.get("type") == "null" for part in retained["properties"][name]["anyOf"])
    unresolved = components["UnresolvedDeletionStatusResponse"]
    assert unresolved["additionalProperties"] is False
    assert set(unresolved["required"]) == set(unresolved["properties"]) == {"outcome"}
    for status in ("400", "401", "403", "422", "500", "503"):
        assert set(operation["responses"][status]["content"]) == {"application/problem+json"}


def test_project_metadata_contract_keeps_optional_replacements_nonnullable_and_legacy_responses_unbounded() -> (
    None
):
    schema = create_app().openapi()
    request = schema["components"]["schemas"]["ProjectMetadataUpdateRequest"]
    assert request["additionalProperties"] is False
    assert request["required"] == ["expectedMetadataRevision"]
    assert request["properties"]["name"]["type"] == "string"
    assert request["properties"]["name"]["maxLength"] == 63
    assert request["properties"]["displayName"]["type"] == "string"
    assert request["properties"]["displayName"]["maxLength"] == 128
    response = schema["components"]["schemas"]["ProjectMetadataResponse"]
    assert "maxLength" not in response["properties"]["displayName"]
    assert any(part.get("type") == "null" for part in response["properties"]["name"]["anyOf"])


def test_metadata_patch_declares_its_actual_framing_problems() -> None:
    operation = create_app().openapi()["paths"]["/v1/projects/{project_id}/metadata"]["patch"]
    for status in ("413", "415"):
        assert operation["responses"][status]["content"] == {
            "application/problem+json": {"schema": {"$ref": "#/components/schemas/ProblemDetails"}}
        }


def test_project_creation_contract_keeps_strict_input_and_exact_original_grant_receipt() -> None:
    schema = create_app().openapi()
    components = schema["components"]["schemas"]
    request = components["ProjectCreationRequest"]
    assert request["additionalProperties"] is False
    assert set(request["required"]) == {
        "organizationId",
        "expectedAccessRevision",
        "name",
        "displayName",
    }
    assert request["properties"]["name"]["maxLength"] == 63
    assert request["properties"]["displayName"]["maxLength"] == 128
    revision = request["properties"]["expectedAccessRevision"]
    assert revision["type"] == "integer" and revision["minimum"] == 0
    assert revision["maximum"] == 2**53 - 1
    response = components["ProjectCreationResponse"]
    assert set(response["required"]) == {
        "operationId",
        "idempotencyExpiresAt",
        "organizationId",
        "projectId",
        "name",
        "displayName",
        "accessRevision",
        "metadataRevision",
        "initialGrants",
    }
    assert response["properties"]["accessRevision"]["const"] == 1
    assert response["properties"]["metadataRevision"]["const"] == 0
    grants = response["properties"]["initialGrants"]
    assert grants["minItems"] == grants["maxItems"] == 18
    assert components["InitialProjectGrantResponse"]["properties"]["canGrant"]["const"] is True
    action = components["InitialProjectGrantResponse"]["properties"]["actionId"]
    assert action == {"$ref": "#/components/schemas/ProjectAction"}
    assert len(components["ProjectAction"]["enum"]) == 18
    assert components["ProjectGrantTargetResponse"]["properties"]["kind"]["const"] == "project"
    operation = schema["paths"]["/v1/projects"]["post"]
    assert operation["operationId"] == "createProject"
    assert operation["responses"]["201"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProjectCreationResponse"
    }
    for status in ("400", "401", "403", "404", "409", "413", "415", "422", "503"):
        assert set(operation["responses"][status]["content"]) == {"application/problem+json"}


def test_own_organization_contract_exposes_only_bounded_supported_assignments() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/v1/my-organization-access"]["get"]
    assert operation["operationId"] == "getMyOrganizationAccess"
    response = schema["components"]["schemas"]["MyOrganizationAccessResponse"]
    assert set(response["required"]) == {
        "organizationId",
        "principalId",
        "accessRevision",
        "grants",
    }
    assert response["properties"]["grants"]["maxItems"] == 4
    grants = schema["components"]["schemas"]["OwnOrganizationGrantResponse"]
    assert grants["properties"]["actionId"] == {"$ref": "#/components/schemas/OrganizationAction"}
    assert set(schema["components"]["schemas"]["OrganizationAction"]["enum"]) == {
        "admit-users",
        "suspend-users",
        "restore-users",
        "create-projects",
    }


def test_project_deletion_contract_preserves_original_admission_and_lookup_tag() -> None:
    """Describe bodyless admission without exposing execution or physical completion."""
    schema = create_app().openapi()
    operation = schema["paths"]["/v1/projects/{project_id}"]["delete"]
    assert operation["operationId"] == "deleteProject"
    assert "requestBody" not in operation
    assert operation["security"] == [{"KratosSession": []}, {"ProductBearer": []}]
    assert operation["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ProjectDeletionAdmissionResponse"
    }
    response = schema["components"]["schemas"]["ProjectDeletionAdmissionResponse"]
    fields = {
        "operationId",
        "idempotencyExpiresAt",
        "projectId",
        "accessRevision",
        "admissionConfirmed",
        "accessBlocked",
    }
    assert response["additionalProperties"] is False
    assert set(response["required"]) == set(response["properties"]) == fields
    assert {
        part.get("type") for part in response["properties"]["idempotencyExpiresAt"]["anyOf"]
    } == {"string", "null"}
    for field in ("admissionConfirmed", "accessBlocked"):
        assert response["properties"][field]["const"] is True
    revision = response["properties"]["accessRevision"]
    assert (revision["minimum"], revision["maximum"]) == (0, 2**53 - 1)
    assert (
        "project_deletion"
        in schema["components"]["schemas"]["OperationLookupAuthorityFamily"]["enum"]
    )
