import json
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import FastAPI, File, Form, Query, UploadFile
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from inframeld_backend.main import create_app
from inframeld_backend.shared.http.error_handlers import register_error_handlers
from inframeld_backend.shared.http.pagination import PageResponse, PaginationQuery
from inframeld_backend.shared.http.problem_definitions import VALIDATION_ERROR_PROBLEM
from inframeld_backend.shared.http.problem_openapi import (
    configure_problem_openapi,
    problem_responses,
)
from inframeld_backend.shared.http.request_context import RequestContextMiddleware

CONTRACT_PATH = (
    Path(__file__).resolve().parents[5] / "contracts" / "openapi" / "v1" / "inframeld-v1.json"
)


class ContractFixturePayload(BaseModel):
    required_name: str = Field(min_length=1, max_length=40, pattern="^[a-z]+$")
    required_nullable: str | None
    optional_nullable: str | None = None
    score: float = Field(ge=0, le=1)
    choice: str | int


def _create_schema_fixture_app() -> FastAPI:
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    configure_problem_openapi(application)

    @application.post(
        "/contract-fixture/payload",
        operation_id="contractFixturePayload",
        responses=problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def contract_fixture_payload(payload: ContractFixturePayload) -> ContractFixturePayload:
        return payload

    @application.post(
        "/contract-fixture/upload",
        operation_id="contractFixtureUpload",
        responses=problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def contract_fixture_upload(
        file: Annotated[UploadFile, File(description="fixture upload")],
        label: Annotated[str, Form(min_length=1, max_length=20)],
    ) -> dict[str, str]:
        return {"filename": file.filename or "", "label": label}

    @application.get(
        "/contract-fixture/page",
        operation_id="contractFixturePage",
        responses=problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def contract_fixture_page(
        pagination: Annotated[PaginationQuery, Query()],
    ) -> PageResponse[int]:
        return PageResponse[int](items=[pagination.limit], next_cursor=None)

    return application


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


def test_schema_fixture_preserves_native_field_semantics() -> None:
    """Prove native OpenAPI preserves required, nullable, union and field constraints."""

    schema = _create_schema_fixture_app().openapi()
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

    schema = _create_schema_fixture_app().openapi()
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
    application = _create_schema_fixture_app()

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
    application = _create_schema_fixture_app()

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
    schema = _create_schema_fixture_app().openapi()
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
    schema = _create_schema_fixture_app().openapi()
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
