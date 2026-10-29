"""Verify committed OpenAPI output and generated HTTP schema conventions."""

import json
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from tests.support.openapi_schema_fixture import create_schema_fixture_app

from inframeld_backend.bootstrap.application_factory import create_app

CONTRACT_PATH = (
    Path(__file__).resolve().parents[5] / "contracts" / "openapi" / "v1" / "inframeld-v1.json"
)


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
        ("/v1/projects/{project_id}/grants", "post"),
        ("/v1/operations/lookup", "post"),
    ],
)
def test_human_routes_declare_cookie_or_bearer_and_authentication_errors(
    path: str, method: str
) -> None:
    """Tell clients they can use either human credential and how authentication failures look."""
    schema = create_app().openapi()
    operation = schema["paths"][path][method]

    assert operation["security"] == [
        {"KratosSession": []},
        {"HumanBearer": []},
    ]
    schemes = schema["components"]["securitySchemes"]
    assert schemes["KratosSession"]["type"] == "apiKey"
    assert schemes["KratosSession"]["in"] == "cookie"
    assert schemes["KratosSession"]["name"] == "ory_kratos_session"
    assert schemes["HumanBearer"]["type"] == "http"
    assert schemes["HumanBearer"]["scheme"] == "bearer"

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
