from dataclasses import replace
from typing import override
from uuid import uuid4

from sqlalchemy import DateTime, delete, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.document_id import DocumentId
from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
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
from inframeld_backend.knowledge.application.protocols.document_upload_repository import (
    DocumentUploadRepository,
)
from inframeld_backend.knowledge.infrastructure.rows.document_group_row import DocumentGroupRow
from inframeld_backend.knowledge.infrastructure.rows.document_row import DocumentRow
from inframeld_backend.knowledge.infrastructure.rows.document_upload_group_row import (
    DocumentUploadGroupRow,
)
from inframeld_backend.knowledge.infrastructure.rows.document_upload_row import DocumentUploadRow
from inframeld_backend.knowledge.infrastructure.rows.document_version_row import DocumentVersionRow
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    IdempotencyKeyReusedError,
)
from inframeld_backend.shared.application.protocols.artifact_attempt_repository import (
    ArtifactAttemptRepository,
)
from inframeld_backend.shared.application.services.artifact_allocation_service import (
    ArtifactAllocationService,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.mappers.postgres_artifact_attempt_mapper import (
    PostgresArtifactAttemptMapper,
)
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow

_MAX_DOCUMENTS = 200


class PostgresDocumentUploadRepository(DocumentUploadRepository):
    """Persist admission under the caller's authorized Organization and Project turns."""

    def __init__(
        self,
        session: AsyncSession,
        artifact_allocation_service: ArtifactAllocationService,
        artifact_attempt_repository: ArtifactAttemptRepository,
    ) -> None:
        self._session = session
        self._artifact_allocation_service = artifact_allocation_service
        self._artifact_attempt_repository = artifact_attempt_repository

    @override
    async def reserve(
        self, *, scope: ArtifactScopeDTO, actor: PrincipalId, command: UploadDocumentCommand
    ) -> DocumentUploadRecordDTO:
        original = await self._find_original(scope, actor, command)
        if original is not None:
            return await self._reconcile_retired_original(original, await self._record(original))

        await self._reconcile_retired(scope)
        documents = await self._session.scalar(
            select(func.count())
            .select_from(DocumentRow)
            .where(DocumentRow.installation_id == scope.installation_id.value)
        )
        pending = await self._session.scalar(
            select(func.count())
            .select_from(DocumentUploadRow)
            .where(
                DocumentUploadRow.installation_id == scope.installation_id.value,
                DocumentUploadRow.state == DocumentUploadState.PENDING.value,
            )
        )
        if documents is None or pending is None:
            raise DependencyUnavailableError("The current Document count cannot be confirmed.")
        if documents + pending >= _MAX_DOCUMENTS:
            raise ConflictError("The installation has no available Document slots.")

        attempt_id = ArtifactAttemptId(uuid4())
        allocation = await self._artifact_allocation_service.allocate_in_transaction(
            scope=scope,
            artifact_id=ArtifactId(uuid4()),
            attempt_id=attempt_id,
            reservation_id=ArtifactStagingReservationId(uuid4()),
            obligation_id=ArtifactCleanupObligationId(uuid4()),
            origin=UnadmittedStagingArtifactOriginDTO(attempt_id, command.request_id),
        )
        row = DocumentUploadRow(
            operation_id=str(uuid4()),
            installation_id=scope.installation_id.value,
            organization_id=scope.organization_id.value,
            project_id=scope.project_id.value,
            actor_principal_id=actor.value,
            request_key=command.key.value,
            request_id=command.request_id.value,
            document_id=uuid4(),
            version_id=uuid4(),
            artifact_id=allocation.reservation.artifact_id.value,
            attempt_id=attempt_id.value,
            reservation_id=allocation.reservation.reservation_id.value,
            obligation_id=allocation.cleanup_binding.obligation_id.value,
            cleanup_job_id=allocation.cleanup_job_id.value,
            filename=command.filename,
            group_ids=[group.value for group in command.audience.group_ids],
            state=DocumentUploadState.PENDING.value,
        )
        self._session.add(row)
        await self._session.flush()
        self._session.add_all(
            DocumentUploadGroupRow(
                operation_id=row.operation_id, project_id=row.project_id, group_id=group
            )
            for group in row.group_ids
        )
        await self._session.flush()
        return DocumentUploadRecordDTO(
            self._result(row), allocation, DocumentUploadState.PENDING, created=True
        )

    @override
    async def read_original(
        self, *, scope: ArtifactScopeDTO, actor: PrincipalId, command: UploadDocumentCommand
    ) -> DocumentUploadRecordDTO:
        row = await self._find_original(scope, actor, command)
        if row is None:
            raise DependencyUnavailableError("The original upload is unavailable.")
        return await self._record(row)

    @override
    async def admit(
        self, *, record: DocumentUploadRecordDTO, verified: VerifiedArtifactDTO
    ) -> None:
        row = await self._require_pending(record)
        sealed = record.allocation.reservation
        if (
            verified.attempt.length != sealed.length
            or verified.attempt.digest != sealed.digest
            or not sealed.put_confirmed
            or sealed.published
        ):
            raise ConflictError("The original verified source is unavailable for admission.")
        await self._artifact_attempt_repository.publish_verified(record.allocation, verified)

        self._session.add(
            DocumentRow(
                id=row.document_id,
                installation_id=row.installation_id,
                organization_id=row.organization_id,
                project_id=row.project_id,
            )
        )
        await self._session.flush()
        self._session.add(
            DocumentVersionRow(
                id=row.version_id,
                installation_id=row.installation_id,
                organization_id=row.organization_id,
                project_id=row.project_id,
                document_id=row.document_id,
                attempt_id=row.attempt_id,
                filename=row.filename,
                media_type="application/pdf",
                length=verified.attempt.length,
                digest=verified.attempt.digest.value,
            )
        )
        self._session.add_all(
            DocumentGroupRow(document_id=row.document_id, project_id=row.project_id, group_id=group)
            for group in row.group_ids
        )
        self._session.add(
            AccessAuditEventRow(
                id=uuid4(),
                organization_id=row.organization_id,
                project_id=row.project_id,
                actor_kind=PrincipalKind.HUMAN.value,
                actor_principal_id=row.actor_principal_id,
                action=AccessGroupAction.ADD_DOCUMENTS.value,
                event_type="document_uploaded",
                target_kind="document",
                target_id=row.document_id,
                correlation_id=row.operation_id,
                after_values={"document_version_id": str(row.version_id)},
            )
        )
        row.state = DocumentUploadState.ADMITTED.value
        await self._remove_pending_groups(row)
        await self._session.flush()

    @override
    async def decline(self, *, record: DocumentUploadRecordDTO) -> None:
        row = await self._require_pending(record)
        current = (await self._record(row)).allocation.reservation
        if (
            current.length is not None
            or current.digest is not None
            or current.put_pending
            or current.put_confirmed
            or current.published
            or not await self._has_no_document(row)
        ):
            raise ConflictError("The invalid upload cannot be confirmed unused.")
        await self._mark_unused(row)

    async def _find_original(
        self, scope: ArtifactScopeDTO, actor: PrincipalId, command: UploadDocumentCommand
    ) -> DocumentUploadRow | None:
        row = await self._session.scalar(
            select(DocumentUploadRow)
            .where(
                DocumentUploadRow.installation_id == scope.installation_id.value,
                DocumentUploadRow.organization_id == scope.organization_id.value,
                DocumentUploadRow.project_id == scope.project_id.value,
                DocumentUploadRow.actor_principal_id == actor.value,
                DocumentUploadRow.request_key == command.key.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is not None and (
            row.filename != command.filename
            or row.group_ids != [group.value for group in command.audience.group_ids]
        ):
            raise IdempotencyKeyReusedError()
        return row

    async def _record(self, row: DocumentUploadRow) -> DocumentUploadRecordDTO:
        observed = (
            (
                await self._session.execute(
                    select(
                        ArtifactAttemptRow,
                        ArtifactStagingReservationRow,
                        ArtifactCleanupObligationRow,
                        func.clock_timestamp(type_=DateTime(timezone=True)),
                    )
                    .join(
                        ArtifactStagingReservationRow,
                        ArtifactStagingReservationRow.attempt_id == ArtifactAttemptRow.id,
                    )
                    .join(
                        ArtifactCleanupObligationRow,
                        ArtifactCleanupObligationRow.staging_reservation_id
                        == ArtifactStagingReservationRow.id,
                    )
                    .join(
                        DurableJobRow,
                        DurableJobRow.cleanup_obligation_id == ArtifactCleanupObligationRow.id,
                    )
                    .where(
                        ArtifactAttemptRow.id == row.attempt_id,
                        ArtifactAttemptRow.artifact_id == row.artifact_id,
                        ArtifactAttemptRow.installation_id == row.installation_id,
                        ArtifactAttemptRow.organization_id == row.organization_id,
                        ArtifactAttemptRow.project_id == row.project_id,
                        ArtifactStagingReservationRow.id == row.reservation_id,
                        ArtifactCleanupObligationRow.id == row.obligation_id,
                        DurableJobRow.id == row.cleanup_job_id,
                        DurableJobRow.binding_kind == "artifact_cleanup",
                        DurableJobRow.installation_id == row.installation_id,
                        DurableJobRow.organization_id == row.organization_id,
                        DurableJobRow.project_id == row.project_id,
                        DurableJobRow.request_id == row.request_id,
                    )
                    .execution_options(populate_existing=True)
                )
            )
            .tuples()
            .one_or_none()
        )
        if observed is None:
            raise DependencyUnavailableError("The original upload storage binding is unavailable.")
        attempt, reservation, obligation, observed_at = observed
        stage = PostgresArtifactAttemptMapper.reservation(attempt, reservation, observed_at)
        binding = PostgresJobBindingMapper.cleanup(obligation)
        if (
            binding.kind is not ArtifactCleanupKind.ABANDONED_STAGING
            or binding.scope != stage.scope
            or not isinstance(binding.origin, UnadmittedStagingArtifactOriginDTO)
            or binding.origin.attempt_id != stage.attempt_id
            or binding.origin.request_id.value != row.request_id
            or obligation.transfer_deadline != stage.expires_at
        ):
            raise DependencyUnavailableError("The original upload storage binding has changed.")
        return DocumentUploadRecordDTO(
            self._result(row),
            ArtifactAllocationDTO(stage, binding, JobId(row.cleanup_job_id)),
            DocumentUploadState(row.state),
        )

    async def _require_pending(self, record: DocumentUploadRecordDTO) -> DocumentUploadRow:
        row = await self._session.get(
            DocumentUploadRow,
            record.result.operation_id.value,
            with_for_update=True,
            populate_existing=True,
        )
        original = record.allocation.reservation
        if (
            row is None
            or row.state != DocumentUploadState.PENDING.value
            or self._result(row) != record.result
            or row.attempt_id != original.attempt_id.value
            or row.artifact_id != original.artifact_id.value
            or row.installation_id != original.scope.installation_id.value
            or row.organization_id != original.scope.organization_id.value
            or row.project_id != original.scope.project_id.value
            or row.reservation_id != original.reservation_id.value
            or row.obligation_id != record.allocation.cleanup_binding.obligation_id.value
            or row.cleanup_job_id != record.allocation.cleanup_job_id.value
        ):
            raise ConflictError("The original pending upload cannot be confirmed.")
        return row

    async def _reconcile_retired(self, scope: ArtifactScopeDTO) -> None:
        rows = (
            await self._session.scalars(
                select(DocumentUploadRow)
                .join(ArtifactAttemptRow, ArtifactAttemptRow.id == DocumentUploadRow.attempt_id)
                .where(
                    DocumentUploadRow.installation_id == scope.installation_id.value,
                    DocumentUploadRow.organization_id == scope.organization_id.value,
                    DocumentUploadRow.state == DocumentUploadState.PENDING.value,
                    ArtifactAttemptRow.retired.is_(True),
                    ArtifactAttemptRow.published.is_(False),
                )
                .with_for_update(of=DocumentUploadRow)
                .limit(_MAX_DOCUMENTS)
            )
        ).all()
        for row in rows:
            await self._reconcile_retired_original(row, await self._record(row))

    async def _reconcile_retired_original(
        self, row: DocumentUploadRow, record: DocumentUploadRecordDTO
    ) -> DocumentUploadRecordDTO:
        original = record.allocation.reservation
        if (
            record.state is DocumentUploadState.PENDING
            and original.retired
            and not original.published
            and await self._has_no_document(row)
        ):
            await self._mark_unused(row)
            return replace(record, state=DocumentUploadState.UNUSED)
        return record

    async def _has_no_document(self, row: DocumentUploadRow) -> bool:
        any_document = exists().where(DocumentRow.id == row.document_id)
        any_version = exists().where(
            (DocumentVersionRow.id == row.version_id)
            | (DocumentVersionRow.document_id == row.document_id)
        )
        return await self._session.scalar(select(~any_document & ~any_version)) is True

    async def _mark_unused(self, row: DocumentUploadRow) -> None:
        row.state = DocumentUploadState.UNUSED.value
        await self._remove_pending_groups(row)
        await self._session.flush()

    async def _remove_pending_groups(self, row: DocumentUploadRow) -> None:
        await self._session.execute(
            delete(DocumentUploadGroupRow).where(
                DocumentUploadGroupRow.operation_id == row.operation_id,
                DocumentUploadGroupRow.project_id == row.project_id,
            )
        )

    @staticmethod
    def _result(row: DocumentUploadRow) -> DocumentUploadResultDTO:
        return DocumentUploadResultDTO(
            OperationId(row.operation_id),
            ProjectId(row.project_id),
            DocumentId(row.document_id),
            DocumentVersionId(row.version_id),
        )
