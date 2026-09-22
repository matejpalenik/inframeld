import json
from pathlib import Path
from typing import Annotated, Any, cast

from fastapi import FastAPI, File, Form, UploadFile
from pydantic import BaseModel, Field

from inframeld_backend.main import create_app

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

    @application.post("/contract-fixture/payload", operation_id="contractFixturePayload")
    async def contract_fixture_payload(payload: ContractFixturePayload) -> ContractFixturePayload:
        return payload

    @application.post("/contract-fixture/upload", operation_id="contractFixtureUpload")
    async def contract_fixture_upload(
        file: Annotated[UploadFile, File(description="fixture upload")],
        label: Annotated[str, Form(min_length=1, max_length=20)],
    ) -> dict[str, str]:
        return {"filename": file.filename or "", "label": label}

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
