from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import override
from uuid import UUID

import httpx2
import pytest
from fastapi import FastAPI
from pydantic import HttpUrl
from tests.support.application_account_scenarios import MockApplicationAccountAuthenticator
from tests.support.artifact_scenarios import MockArtifactCapacityReader
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_application_authenticator import MockApplicationAuthenticator
from tests.support.seaweedfs_fixture import storage_settings

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.value_objects.application_key_credential import (
    ApplicationKeyCredential,
)
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.http.dependencies.csrf_protection_dependency import (
    CSRFProtectionDependency,
)
from inframeld_backend.access.http.dependencies.product_access_dependency import (
    ProductAccessDependency,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.bootstrap.document_upload_composition import open_document_upload
from inframeld_backend.knowledge.application.commands.upload_document_command import (
    UploadDocumentCommand,
)
from inframeld_backend.knowledge.application.dtos.document_upload_result_dto import (
    DocumentUploadResultDTO,
)
from inframeld_backend.knowledge.application.errors.document_upload_errors import (
    InvalidPdfUploadError,
    PdfUploadTooLargeError,
)
from inframeld_backend.knowledge.application.protocols.document_uploader import DocumentUploader
from inframeld_backend.knowledge.application.services.pdf_upload_stream import PdfUploadStream
from inframeld_backend.knowledge.http.routes.document_upload_routes import (
    create_document_upload_router,
)
from inframeld_backend.shared.application.errors.application_errors import (
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
)
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactIntegrityError,
    ArtifactStoreUnavailableError,
    ArtifactWriteOutcomeUnknownError,
)
from inframeld_backend.shared.application.errors.job_errors import JobQueueFullError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.artifact_staging_settings import (
    ArtifactStagingSettings,
)

_PROJECT = UUID(int=1)
_GROUP_ONE = UUID(int=2)
_GROUP_TWO = UUID(int=3)
_ROUTE = f"/v1/projects/{_PROJECT}/documents"
_QUERY = f"?groupIds={_GROUP_ONE}&groupIds={_GROUP_TWO}&filename=r%C3%A8glement.pdf"
_RESULT = DocumentUploadResultDTO(
    OperationId("original"),
    ProjectId(_PROJECT),
    DocumentId(UUID(int=4)),
    DocumentVersionId(UUID(int=5)),
    datetime(2026, 1, 1, tzinfo=UTC),
)
_HEADERS = [
    ("Authorization", "Bearer human-token"),
    ("Idempotency-Key", "original"),
    ("Content-Type", "Application/PDF"),
]
_PDF = (b"%PDF-1.", b"7\n\xff", b"the validated source")


class _Uploader(DocumentUploader):
    def __init__(
        self,
        *,
        error: Exception | None = None,
        result: DocumentUploadResultDTO = _RESULT,
    ) -> None:
        self.error = error
        self.result = result
        self.events: list[str] = []
        self.command: UploadDocumentCommand | None = None
        self.access: AccessContextDTO | None = None
        self.content: list[bytes] = []

    @asynccontextmanager
    async def open(self) -> AsyncGenerator[DocumentUploader]:
        self.events.append("open")
        yield self

    @override
    async def upload(
        self,
        *,
        access: AccessContextDTO,
        command: UploadDocumentCommand,
        chunks: AsyncIterable[bytes],
    ) -> DocumentUploadResultDTO:
        self.events.append("upload")
        self.command, self.access = command, access
        if self.error is not None:
            raise self.error
        stream = PdfUploadStream(command.filename, chunks)
        self.content.extend([chunk async for chunk in stream.read()])
        return self.result

    async def body(self) -> AsyncIterator[bytes]:
        self.events.append("receive")
        for chunk in _PDF:
            yield chunk


def _app(
    open_uploader: Callable[[], AbstractAsyncContextManager[DocumentUploader]] | None,
) -> FastAPI:
    actor = PrincipalId(UUID(int=6))
    browser = AccessContextDTO(actor, MockAuthenticationEvidence.browser())
    bearer = AccessContextDTO(actor, MockAuthenticationEvidence.human_oauth())
    application = AccessContextDTO(actor, MockAuthenticationEvidence.application_key())
    authentication = MockApplicationAccountAuthenticator(browser, bearer)
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)
    app.include_router(
        create_document_upload_router(
            ProductAccessDependency(
                authentication,
                CSRFProtectionDependency((HttpUrl("https://account.test"),)),
                access_token_authenticator=authentication,
                application_authenticator=MockApplicationAuthenticator(application),
            ),
            open_uploader,
        )
    )
    return app


@pytest.mark.asyncio
@pytest.mark.parametrize("legacy", [False, True])
async def test_upload_maps_raw_bytes_and_returns_original_required_nullable_deadline(
    legacy: bool,
) -> None:
    result = replace(_RESULT, idempotency_expires_at=None) if legacy else _RESULT
    uploader = _Uploader(result=result)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(uploader.open)), base_url="https://api.test"
    ) as client:
        response = await client.post(_ROUTE + _QUERY, headers=_HEADERS, content=uploader.body())

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {
        "operationId": "original",
        "projectId": str(_PROJECT),
        "documentId": str(_RESULT.document_id.value),
        "documentVersionId": str(_RESULT.version_id.value),
        "idempotencyExpiresAt": None if legacy else "2026-01-01T00:00:00Z",
    }
    assert uploader.events == ["open", "upload", "receive"]
    assert b"".join(uploader.content) == b"".join(_PDF)
    assert uploader.command is not None
    assert uploader.command.request_id.value == UUID(response.headers["x-request-id"])
    assert uploader.command.filename == "règlement.pdf"
    assert tuple(group.value for group in uploader.command.audience.group_ids) == (
        _GROUP_ONE,
        _GROUP_TWO,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("headers", "status"),
    [
        (_HEADERS[1:], 401),
        ([*_HEADERS[1:], ("Cookie", "ory_kratos_session=browser")], 403),
        (
            [
                *_HEADERS[1:],
                ("Authorization", f"Bearer {ApplicationKeyCredential.generate().value}"),
            ],
            403,
        ),
        ([*_HEADERS, ("Idempotency-Key", "duplicate")], 422),
        ([*_HEADERS, ("Content-Type", "application/pdf")], 415),
        ([*_HEADERS, ("Content-Encoding", "gzip")], 415),
        ([*_HEADERS[:2], ("Content-Type", "application/pdf; charset=utf-8")], 415),
        ([*_HEADERS[:2], ("Content-Type", "multipart/form-data")], 415),
    ],
)
async def test_invalid_authentication_or_framing_does_not_read_or_open_upload(
    headers: list[tuple[str, str]], status: int
) -> None:
    uploader = _Uploader()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(uploader.open)), base_url="https://api.test"
    ) as client:
        response = await client.post(_ROUTE + _QUERY, headers=headers, content=uploader.body())

    assert response.status_code == status
    assert uploader.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        _QUERY + "&filename=another.pdf",
        f"?groupIds={_GROUP_ONE}&filename=%FF.pdf",
        "?groupIds=invalid&filename=handbook.pdf",
        "?filename=handbook.pdf",
        f"?groupIds={_GROUP_ONE}&groupIds={_GROUP_ONE}&filename=handbook.pdf",
    ],
)
async def test_invalid_query_does_not_receive_bytes(query: str) -> None:
    uploader = _Uploader()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(uploader.open)), base_url="https://api.test"
    ) as client:
        response = await client.post(_ROUTE + query, headers=_HEADERS, content=uploader.body())

    assert response.status_code == 422
    assert uploader.events == []


@pytest.mark.asyncio
async def test_cookie_requires_and_accepts_existing_csrf_proof() -> None:
    uploader = _Uploader()
    headers = [
        *_HEADERS[1:],
        ("Cookie", "ory_kratos_session=browser"),
        ("Origin", "https://account.test"),
        ("X-Inframeld-CSRF", "1"),
    ]
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(uploader.open)), base_url="https://api.test"
    ) as client:
        response = await client.post(_ROUTE + _QUERY, headers=headers, content=uploader.body())

    assert response.status_code == 201
    assert uploader.access is not None
    assert uploader.access.authentication_evidence == MockAuthenticationEvidence.browser()


@pytest.mark.asyncio
async def test_unconfigured_storage_returns_unavailable_without_request_body_read() -> None:
    source = _Uploader()
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(None)), base_url="https://api.test"
    ) as client:
        response = await client.post(_ROUTE + _QUERY, headers=_HEADERS, content=source.body())

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
    assert source.events == []


@pytest.mark.asyncio
async def test_unusable_backing_reports_unavailable_before_request_body_read(
    tmp_path: Path,
) -> None:
    staging_root = tmp_path / "staging"
    staging_root.mkdir(mode=0o700)
    (staging_root / ".locks").touch(mode=0o600)
    source = _Uploader()
    capacity = MockArtifactCapacityReader()
    database = Database(get_settings().database)

    @asynccontextmanager
    async def opener() -> AsyncGenerator[DocumentUploader]:
        async with open_document_upload(
            database, ArtifactStagingSettings(root=staging_root), storage_settings(), capacity
        ) as service:
            yield service

    try:
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=_app(opener), raise_app_exceptions=False),
            base_url="https://api.test",
        ) as client:
            response = await client.post(_ROUTE + _QUERY, headers=_HEADERS, content=source.body())
    finally:
        await database.shutdown()

    assert response.status_code == 503
    assert response.json()["code"] == "dependency_unavailable"
    assert source.events == [] and capacity.reads == 0


@pytest.mark.asyncio
async def test_oversize_stream_is_rejected_by_the_received_byte_count() -> None:
    uploader = _Uploader()

    async def body() -> AsyncIterator[bytes]:
        yield b"%PDF-2.0\n"
        for _ in range(25):
            yield b"x" * 1024**2

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(uploader.open)), base_url="https://api.test"
    ) as client:
        response = await client.post(_ROUTE + _QUERY, headers=_HEADERS, content=body())

    assert response.status_code == 413


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [
        (PdfUploadTooLargeError("protected"), 413, "http_error"),
        (InvalidPdfUploadError("protected"), 422, "invalid_input"),
        (ArtifactCapacityError("protected"), 503, "dependency_unavailable"),
        (ArtifactIntegrityError("protected"), 503, "dependency_unavailable"),
        (ArtifactStoreUnavailableError("protected"), 503, "dependency_unavailable"),
        (ArtifactWriteOutcomeUnknownError("protected"), 503, "dependency_unavailable"),
        (JobQueueFullError("protected"), 503, "dependency_unavailable"),
        (IdempotencyKeyReusedError("protected"), 409, "idempotency_key_reused"),
        (IdempotencyInProgressError(_RESULT.operation_id, 3), 409, "idempotency_in_progress"),
        (
            ExceptionGroup(
                "protected", [PdfUploadTooLargeError("protected"), RuntimeError("protected")]
            ),
            500,
            "internal_error",
        ),
    ],
)
async def test_errors_preserve_public_classification_without_exposing_source_or_cleanup(
    failure: Exception, status: int, code: str
) -> None:
    uploader = _Uploader(error=failure)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(uploader.open), raise_app_exceptions=False),
        base_url="https://api.test",
    ) as client:
        response = await client.post(_ROUTE + _QUERY, headers=_HEADERS, content=uploader.body())

    assert response.status_code == status
    assert response.json()["code"] == code
    assert "protected" not in response.text
    if isinstance(failure, IdempotencyInProgressError):
        assert response.headers["retry-after"] == "3"
        assert response.json()["operationId"] == "original"


def test_native_contract_declares_binary_pdf_and_typed_explicit_audience() -> None:
    schema = create_app().openapi()
    upload = schema["paths"]["/v1/projects/{project_id}/documents"]["post"]
    assert upload["operationId"] == "uploadDocument"
    assert upload["requestBody"] == {
        "required": True,
        "content": {"application/pdf": {"schema": {"type": "string", "format": "binary"}}},
    }
    parameters = {param["name"]: param for param in upload["parameters"]}
    assert parameters["groupIds"]["required"] is True
    assert parameters["groupIds"]["schema"]["items"] == {"type": "string", "format": "uuid"}
    assert parameters["filename"]["required"] is True
    response = schema["components"]["schemas"]["DocumentUploadResponse"]
    assert "idempotencyExpiresAt" in response["required"]
    assert {"type": "null"} in response["properties"]["idempotencyExpiresAt"]["anyOf"]
