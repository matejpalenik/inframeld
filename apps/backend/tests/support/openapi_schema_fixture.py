"""Share native FastAPI schema fixtures across backend and generated-client tests."""

from typing import Annotated

from fastapi import FastAPI, File, Form, Query, UploadFile
from pydantic import BaseModel, Field
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from inframeld_backend.shared.http.definitions.problem_catalogue import VALIDATION_ERROR_PROBLEM
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.http.openapi.problem_openapi import (
    configure_problem_openapi,
    problem_responses,
)
from inframeld_backend.shared.http.requests.pagination_query import PaginationQuery
from inframeld_backend.shared.http.responses.page_response import PageResponse


class ContractFixturePayload(BaseModel):
    """Exercise required, nullable, union, and constrained fields on a test-only route."""

    required_name: str = Field(min_length=1, max_length=40, pattern="^[a-z]+$")
    required_nullable: str | None
    optional_nullable: str | None = None
    score: float = Field(ge=0, le=1)
    choice: str | int


class ContractFixtureReadyResponseDTO(BaseModel):
    value: str


class ContractFixtureAcceptedResponseDTO(BaseModel):
    job_id: str = Field(alias="jobId")


def create_schema_fixture_app() -> FastAPI:
    """Register test-only payload, upload, and pagination routes for schema assertions."""
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    configure_problem_openapi(application)

    @application.get(
        "/contract-fixture/variants",
        operation_id="contractFixtureVariants",
        response_model=ContractFixtureReadyResponseDTO,
        responses={
            202: {"model": ContractFixtureAcceptedResponseDTO},
            204: {"description": "No content"},
            "default": {"model": ContractFixtureAcceptedResponseDTO},
        },
    )
    async def variant_response(mode: str = "ready") -> Response:
        if mode == "empty":
            return Response(status_code=204)

        if mode in {"accepted", "fallback"}:
            body = ContractFixtureAcceptedResponseDTO(jobId="job-123")
            return JSONResponse(
                body.model_dump(by_alias=True), status_code=202 if mode == "accepted" else 201
            )

        return JSONResponse(ContractFixtureReadyResponseDTO(value="ready").model_dump())

    @application.get(
        "/contract-fixture/fallback",
        operation_id="contractFixtureFallback",
        status_code=204,
        response_class=Response,
        responses={
            404: {"description": "Missing without a body"},
            "default": {
                "description": "Fallback representation",
                "content": {
                    "application/json": {
                        "schema": {"$ref": "#/components/schemas/ContractFixtureReadyResponseDTO"}
                    },
                    "application/vnd.inframeld.job+json": {
                        "schema": {
                            "anyOf": [
                                {"$ref": "#/components/schemas/ContractFixtureAcceptedResponseDTO"},
                                {"type": "null"},
                            ]
                        }
                    },
                },
            },
        },
    )
    async def fallback_response(request: Request, mode: str = "ready") -> Response:
        if mode == "empty":
            return Response(status_code=204)

        if request.headers.get("accept") == "application/vnd.inframeld.job+json":
            body = ContractFixtureAcceptedResponseDTO(jobId="job-123")
            return JSONResponse(
                None if mode == "nullable" else body.model_dump(by_alias=True),
                status_code=202,
                media_type="application/vnd.inframeld.job+json",
            )

        return JSONResponse(
            ContractFixtureReadyResponseDTO(value="ready").model_dump(), status_code=201
        )

    @application.get(
        "/contract-fixture/media",
        operation_id="contractFixtureMedia",
        response_model=ContractFixtureReadyResponseDTO,
        responses={
            200: {
                "content": {
                    "application/vnd.inframeld.job+json": {
                        "schema": {
                            "anyOf": [
                                {"$ref": "#/components/schemas/ContractFixtureAcceptedResponseDTO"},
                                {"type": "null"},
                            ]
                        }
                    }
                }
            }
        },
    )
    async def media_response(request: Request) -> Response:
        if request.headers.get("accept") == "application/vnd.inframeld.job+json":
            body = ContractFixtureAcceptedResponseDTO(jobId="job-123")
            return JSONResponse(
                body.model_dump(by_alias=True), media_type="application/vnd.inframeld.job+json"
            )

        return JSONResponse(ContractFixtureReadyResponseDTO(value="ready").model_dump())

    @application.get("/contract-fixture/nullable", operation_id="contractFixtureNullable")
    async def nullable_response() -> ContractFixturePayload | None:
        return None

    @application.get(
        "/contract-fixture/empty",
        operation_id="contractFixtureEmpty",
        status_code=204,
        response_class=Response,
    )
    async def empty_response() -> Response:
        return Response(status_code=204)

    @application.post(
        "/contract-fixture/payload",
        operation_id="contractFixturePayload",
        responses=problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def contract_fixture_payload(payload: ContractFixturePayload) -> ContractFixturePayload:
        """Expose the fixture payload's request and response schemas."""
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
        """Exercise multipart upload schema generation."""
        return {"filename": file.filename or "", "label": label}

    @application.get(
        "/contract-fixture/page",
        operation_id="contractFixturePage",
        responses=problem_responses(VALIDATION_ERROR_PROBLEM),
    )
    async def contract_fixture_page(
        pagination: Annotated[PaginationQuery, Query()],
    ) -> PageResponse[int]:
        """Expose the common pagination query and response contract."""
        return PageResponse[int](items=[pagination.limit], next_cursor=None)

    return application
