from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from typing import Annotated
from urllib.parse import unquote_to_bytes
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_key_authentication_dto import (
    ApplicationKeyAuthenticationDTO,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.access.http.openapi.human_authentication_responses import (
    human_authentication_responses,
)
from inframeld_backend.knowledge.application.errors.document_upload_errors import (
    InvalidPdfUploadError,
    PdfUploadTooLargeError,
)
from inframeld_backend.knowledge.application.protocols.document_uploader import DocumentUploader
from inframeld_backend.knowledge.http.mappers.document_upload_mapper import DocumentUploadMapper
from inframeld_backend.knowledge.http.responses.document_upload_response import (
    DocumentUploadResponse,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    InvalidInputError,
)
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactIntegrityError,
    ArtifactReservationError,
    ArtifactStoreUnavailableError,
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.errors.job_errors import JobQueueFullError
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    ACCESS_DENIED_PROBLEM,
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.dependencies.idempotency_key_dependency import (
    IdempotencyKeyDependency,
)
from inframeld_backend.shared.http.dependencies.request_identity import request_identity
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses

_PDF = "application/pdf"


def create_document_upload_router(
    authenticate: ProductAccessDependency,
    open_uploader: Callable[[], AbstractAsyncContextManager[DocumentUploader]] | None,
) -> APIRouter:
    router = APIRouter()
    key_dependency = IdempotencyKeyDependency()

    @router.post(
        "/v1/projects/{project_id}/documents",
        tags=["knowledge"],
        operation_id="uploadDocument",
        status_code=201,
        description=(
            "Upload one PDF with a human credential and Add documents on every selected group. "
            "The limit is 25 MiB of received file bytes. To recover the original result, "
            "repeat the same Project, group IDs, filename, PDF bytes and Idempotency-Key."
        ),
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {_PDF: {"schema": {"type": "string", "format": "binary"}}},
            },
        },
        responses=human_authentication_responses()
        | problem_responses(ACCESS_DENIED_PROBLEM)
        | problem_responses(CONFLICT_PROBLEM)
        | problem_responses(DEPENDENCY_UNAVAILABLE_PROBLEM)
        | problem_responses(INVALID_INPUT_PROBLEM)
        | problem_responses(RESOURCE_NOT_FOUND_PROBLEM)
        | problem_responses(VALIDATION_ERROR_PROBLEM)
        | problem_responses(for_http_status(413))
        | problem_responses(for_http_status(415)),
    )
    async def upload(
        request: Request,
        response: Response,
        project_id: UUID,
        group_ids: Annotated[list[UUID], Query(alias="groupIds", min_length=1)],
        filename: Annotated[str, Query(min_length=1, max_length=255)],
        access: Annotated[AccessContextDTO, Depends(authenticate)],
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> DocumentUploadResponse:
        if isinstance(access.authentication_evidence, ApplicationKeyAuthenticationDTO):
            raise AccessDeniedError()
        _require_pdf_request(request)
        command = DocumentUploadMapper.command(
            project_id, group_ids, filename, key, request_identity(request)
        )
        if open_uploader is None:
            raise DependencyUnavailableError()

        try:
            async with open_uploader() as uploader:
                result = await uploader.upload(
                    access=access, command=command, chunks=request.stream()
                )
        except PdfUploadTooLargeError:
            raise HTTPException(status_code=413) from None
        except InvalidPdfUploadError:
            raise InvalidInputError() from None
        except (
            ArtifactCapacityError,
            ArtifactIntegrityError,
            ArtifactReservationError,
            ArtifactStoreUnavailableError,
            ArtifactWriteOutcomeUnknownError,
            JobQueueFullError,
            TimeoutError,
        ) as error:
            raise DependencyUnavailableError() from error

        response.headers["Cache-Control"] = "no-store"
        return DocumentUploadMapper.response(result)

    return router


def _require_pdf_request(request: Request) -> None:
    content_types = request.headers.getlist("content-type")
    if (
        len(content_types) != 1
        or content_types[0].strip(" \t").lower() != _PDF
        or "content-encoding" in request.headers
        or "content-transfer-encoding" in request.headers
    ):
        raise HTTPException(status_code=415)

    if len(request.query_params.getlist("filename")) != 1:
        raise InvalidInputError("Exactly one filename is required.")
    try:
        unquote_to_bytes(request.scope["query_string"]).decode("utf-8")
    except UnicodeDecodeError:
        raise InvalidInputError("The upload query must be encoded in UTF-8.") from None
