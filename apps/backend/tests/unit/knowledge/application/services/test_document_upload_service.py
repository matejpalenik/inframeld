from collections.abc import AsyncGenerator, AsyncIterable, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import uuid4

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.domain.value_objects.upload_audience import UploadAudience
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
from inframeld_backend.knowledge.application.services.document_upload_service import (
    DocumentUploadService,
)
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    IdempotencyKeyReusedError,
)
from inframeld_backend.shared.application.protocols.artifact_preparer import ArtifactPreparer
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId

_PDF = b"%PDF-1.7\nexample\n"


class _Scenario(
    TransactionManager, DocumentUploadAuthorizer, DocumentUploadRepository, ArtifactPreparer
):
    def __init__(self) -> None:
        evidence = MockAuthenticationEvidence.human_oauth()
        self.access = AccessContextDTO(PrincipalId(uuid4()), evidence)
        self.scope = ArtifactScopeDTO(
            evidence.installation_id,
            OrganizationId(uuid4()),
            ProjectId(uuid4()),
        )
        self.command = UploadDocumentCommand(
            self.scope.project_id,
            UploadAudience((AccessGroupId(uuid4()),)),
            "handbook.pdf",
            IdempotencyKey("original"),
            RequestId(uuid4()),
        )
        now = datetime.now(UTC)
        attempt = ArtifactAttemptId(uuid4())
        allocation = ArtifactAllocationDTO(
            ArtifactStagingReservationDTO(
                ArtifactStagingReservationId(uuid4()),
                ArtifactId(uuid4()),
                attempt,
                self.scope,
                25 * 1024**2,
                now + timedelta(hours=2),
                now,
            ),
            ArtifactCleanupJobBindingDTO(
                ArtifactCleanupObligationId(uuid4()),
                self.scope,
                ArtifactCleanupKind.ABANDONED_STAGING,
                UnadmittedStagingArtifactOriginDTO(attempt, self.command.request_id),
            ),
            JobId(uuid4()),
        )
        self.original = DocumentUploadRecordDTO(
            DocumentUploadResultDTO(
                OperationId(str(uuid4())),
                self.scope.project_id,
                DocumentId(uuid4()),
                DocumentVersionId(uuid4()),
            ),
            allocation,
            DocumentUploadState.PENDING,
        )
        self.started = False
        self.in_transaction = False
        self.allow = True
        self.block_after_read = False
        self.admitted_during_preparation = False
        self.receipt_deadline = datetime(2026, 1, 1, tzinfo=UTC)
        self.prepare_calls = 0
        self.admissions = 0
        self.source_reads = 0
        self.service = DocumentUploadService(self, self, self, self)

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        assert not self.in_transaction
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False

    @override
    async def require_current(
        self, *, access: AccessContextDTO, command: UploadDocumentCommand
    ) -> ArtifactScopeDTO:
        assert self.in_transaction and access == self.access and command == self.command
        if not self.allow:
            raise AccessDeniedError()
        return self.scope

    @override
    async def reserve(
        self, *, scope: ArtifactScopeDTO, actor: PrincipalId, command: UploadDocumentCommand
    ) -> DocumentUploadRecordDTO:
        assert self.in_transaction and scope == self.scope
        assert actor == self.access.actor_principal_id and command == self.command
        record = replace(self.original, created=not self.started)
        self.started = True
        return record

    @override
    async def read_original(
        self, *, scope: ArtifactScopeDTO, actor: PrincipalId, command: UploadDocumentCommand
    ) -> DocumentUploadRecordDTO:
        assert self.in_transaction and scope == self.scope
        assert actor == self.access.actor_principal_id and command == self.command
        return self.original

    @override
    async def admit(
        self, *, record: DocumentUploadRecordDTO, verified: VerifiedArtifactDTO
    ) -> DocumentUploadResultDTO:
        assert self.in_transaction and record == self.original
        assert verified.attempt.digest == record.allocation.reservation.digest
        self.admissions += 1
        result = replace(record.result, idempotency_expires_at=self.receipt_deadline)
        self.original = replace(record, result=result, state=DocumentUploadState.ADMITTED)
        return result

    @override
    async def decline(self, *, record: DocumentUploadRecordDTO) -> None:
        assert self.in_transaction and record.result == self.original.result
        self.original = replace(self.original, state=DocumentUploadState.UNUSED)

    @override
    async def prepare(
        self, allocation: ArtifactAllocationDTO, chunks: AsyncIterable[bytes]
    ) -> VerifiedArtifactDTO:
        assert not self.in_transaction and allocation == self.original.allocation
        self.prepare_calls += 1
        content = b"".join([chunk async for chunk in chunks])
        original = allocation.reservation
        digest = ArtifactContentDigest.from_content(content)
        self.original = replace(
            self.original,
            allocation=replace(
                allocation, reservation=replace(original, length=len(content), digest=digest)
            ),
        )
        if self.block_after_read:
            self.allow = False
        if self.admitted_during_preparation:
            result = replace(self.original.result, idempotency_expires_at=self.receipt_deadline)
            self.original = replace(
                self.original, result=result, state=DocumentUploadState.ADMITTED
            )
        return VerifiedArtifactDTO(
            ArtifactAttemptDTO(
                original.artifact_id, original.attempt_id, self.scope, len(content), digest
            )
        )

    @override
    async def resume(self, allocation: ArtifactAllocationDTO) -> VerifiedArtifactDTO:
        raise AssertionError("These scenarios do not resume a pending object.")

    async def input(self, content: bytes) -> AsyncIterator[bytes]:
        assert not self.in_transaction and self.started
        self.source_reads += 1
        yield content

    async def upload(self, content: bytes = _PDF) -> DocumentUploadResultDTO:
        return await self.service.upload(
            access=self.access, command=self.command, chunks=self.input(content)
        )


@pytest.mark.asyncio
async def test_original_result_recovers_without_second_preparation_or_admission() -> None:
    scenario = _Scenario()

    original = await scenario.upload()
    assert original.idempotency_expires_at == scenario.receipt_deadline
    scenario.receipt_deadline += timedelta(days=1)
    assert await scenario.upload() == original
    with pytest.raises(IdempotencyKeyReusedError):
        await scenario.upload(_PDF + b"changed")
    assert scenario.prepare_calls == scenario.admissions == 1


@pytest.mark.asyncio
async def test_concurrent_admission_returns_saved_deadline_for_same_original() -> None:
    scenario = _Scenario()
    scenario.admitted_during_preparation = True

    result = await scenario.upload()

    assert result.idempotency_expires_at == scenario.receipt_deadline
    assert scenario.admissions == 0


@pytest.mark.asyncio
async def test_initial_denial_does_not_reserve_or_consume_input() -> None:
    scenario = _Scenario()
    scenario.allow = False

    with pytest.raises(AccessDeniedError):
        await scenario.upload()
    assert not scenario.started
    assert scenario.prepare_calls == scenario.source_reads == 0


@pytest.mark.asyncio
async def test_current_authority_can_deny_admission_after_storage_verification() -> None:
    scenario = _Scenario()
    scenario.block_after_read = True

    with pytest.raises(AccessDeniedError):
        await scenario.upload()
    assert scenario.prepare_calls == 1
    assert scenario.admissions == 0
    assert scenario.original.state is DocumentUploadState.PENDING


@pytest.mark.asyncio
async def test_owned_invalid_input_releases_only_the_pending_slot() -> None:
    scenario = _Scenario()

    with pytest.raises(InvalidPdfUploadError):
        await scenario.upload(b"not a PDF")
    assert scenario.original.state is DocumentUploadState.UNUSED
    assert scenario.admissions == 0
    assert scenario.original.allocation.reservation.digest is None


@pytest.mark.asyncio
@pytest.mark.parametrize("unavailable", ["retired", "released", "at-expiry"])
async def test_unavailable_unsealed_original_stops_before_reading(unavailable: str) -> None:
    scenario = _Scenario()
    scenario.started = True
    allocation = scenario.original.allocation
    stage = allocation.reservation
    stage = replace(
        stage,
        retired=unavailable == "retired",
        released=unavailable == "released",
        observed_at=stage.expires_at if unavailable == "at-expiry" else stage.observed_at,
    )
    scenario.original = replace(
        scenario.original, allocation=replace(allocation, reservation=stage)
    )

    with pytest.raises(ConflictError, match="can no longer be admitted"):
        await scenario.upload()
    assert scenario.prepare_calls == scenario.source_reads == scenario.admissions == 0
