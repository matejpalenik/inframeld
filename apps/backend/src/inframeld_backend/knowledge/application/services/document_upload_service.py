import asyncio
from collections.abc import AsyncIterable
from typing import override

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.knowledge.application.commands.upload_document_command import (
    UploadDocumentCommand,
)
from inframeld_backend.knowledge.application.dtos.document_upload_record_dto import (
    DocumentUploadRecordDTO,
)
from inframeld_backend.knowledge.application.dtos.document_upload_result_dto import (
    DocumentUploadResultDTO,
)
from inframeld_backend.knowledge.application.enums.document_upload_state import DocumentUploadState
from inframeld_backend.knowledge.application.errors.document_upload_errors import (
    InvalidPdfUploadError,
)
from inframeld_backend.knowledge.application.protocols.document_upload_authorizer import (
    DocumentUploadAuthorizer,
)
from inframeld_backend.knowledge.application.protocols.document_upload_repository import (
    DocumentUploadRepository,
)
from inframeld_backend.knowledge.application.protocols.document_uploader import DocumentUploader
from inframeld_backend.knowledge.application.services.pdf_upload_stream import PdfUploadStream
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
)
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactIntegrityError
from inframeld_backend.shared.application.protocols.artifact_preparer import ArtifactPreparer
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class DocumentUploadService(DocumentUploader):
    """Admit one verified PDF using its durable original storage reservation."""

    def __init__(
        self,
        transaction_manager: TransactionManager,
        document_upload_authorizer: DocumentUploadAuthorizer,
        document_upload_repository: DocumentUploadRepository,
        artifact_preparer: ArtifactPreparer,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._document_upload_authorizer = document_upload_authorizer
        self._document_upload_repository = document_upload_repository
        self._artifact_preparer = artifact_preparer

    @override
    async def upload(
        self,
        *,
        access: AccessContextDTO,
        command: UploadDocumentCommand,
        chunks: AsyncIterable[bytes],
    ) -> DocumentUploadResultDTO:
        stream = PdfUploadStream(command.filename, chunks)
        async with asyncio.timeout(5), self._transaction_manager.begin():
            scope = await self._require_scope(access, command)
            record = await self._document_upload_repository.reserve(
                scope=scope, actor=access.actor_principal_id, command=command
            )
            if record.allocation.reservation.scope != scope:
                raise ArtifactIntegrityError("The original upload belongs to another scope.")

        verified = await self._prepare(access, command, record, stream)

        async with asyncio.timeout(5), self._transaction_manager.begin():
            current_scope = await self._require_scope(access, command)
            current = await self._document_upload_repository.read_original(
                scope=current_scope, actor=access.actor_principal_id, command=command
            )
            if current_scope != scope or not current.result.matches_original(record.result):
                raise ArtifactIntegrityError("The original upload changed during verification.")

            self._require_original_content(current, stream)
            if current.state is DocumentUploadState.ADMITTED:
                return current.result
            if current.state is not DocumentUploadState.PENDING or verified is None:
                raise ConflictError("The original upload can no longer be admitted.")

            return await self._document_upload_repository.admit(record=current, verified=verified)

    async def _prepare(
        self,
        access: AccessContextDTO,
        command: UploadDocumentCommand,
        record: DocumentUploadRecordDTO,
        stream: PdfUploadStream,
    ) -> VerifiedArtifactDTO | None:
        if record.state is DocumentUploadState.UNUSED:
            raise ConflictError("The original upload did not admit a Document.")

        if record.created:
            try:
                async with asyncio.timeout(7200):
                    return await self._artifact_preparer.prepare(record.allocation, stream.read())
            except InvalidPdfUploadError as error:
                try:
                    async with asyncio.timeout(5), self._transaction_manager.begin():
                        await self._require_scope(access, command)
                        await self._document_upload_repository.decline(record=record)
                except Exception as settlement:
                    raise ExceptionGroup(
                        "The invalid upload and its local admission settlement both failed.",
                        [error, settlement],
                    ) from None
                raise

        original = record.allocation.reservation
        remaining = (
            7200.0
            if record.state is DocumentUploadState.ADMITTED
            else (original.expires_at - original.observed_at).total_seconds()
        )
        if not 0 < remaining <= 7200 or (
            record.state is DocumentUploadState.PENDING and (original.released or original.retired)
        ):
            raise ConflictError("The original upload can no longer be admitted.")
        if original.digest is None or original.length is None:
            raise IdempotencyInProgressError(record.result.operation_id, retry_after_seconds=3)

        async with asyncio.timeout(remaining):
            async for _ in stream.read():
                pass
            self._require_original_content(record, stream)
            if record.state is DocumentUploadState.ADMITTED:
                return None
            return await self._artifact_preparer.resume(record.allocation)

    async def _require_scope(
        self, access: AccessContextDTO, command: UploadDocumentCommand
    ) -> ArtifactScopeDTO:
        scope = await self._document_upload_authorizer.require_current(
            access=access, command=command
        )
        if scope.project_id != command.project_id:
            raise ArtifactIntegrityError("Upload authority returned another Project.")
        return scope

    @staticmethod
    def _require_original_content(record: DocumentUploadRecordDTO, stream: PdfUploadStream) -> None:
        original = record.allocation.reservation
        if (original.digest, original.length) != (stream.digest, stream.length):
            raise IdempotencyKeyReusedError()
