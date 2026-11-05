from datetime import datetime
from typing import override

from sqlalchemy import DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_obligation_dto import (
    ArtifactCleanupObligationDTO,
)
from inframeld_backend.shared.application.dtos.business_operation_artifact_origin_dto import (
    BusinessOperationArtifactOriginDTO,
)
from inframeld_backend.shared.application.dtos.unadmitted_staging_artifact_origin_dto import (
    UnadmittedStagingArtifactOriginDTO,
)
from inframeld_backend.shared.application.enums.artifact_cleanup_kind import ArtifactCleanupKind
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactReservationError,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_obligation_repository import (
    ArtifactCleanupObligationRepository,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_target_row import (
    ArtifactCleanupTargetRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresArtifactCleanupObligationRepository(ArtifactCleanupObligationRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def create_staging(
        self,
        binding: ArtifactCleanupJobBindingDTO,
        *,
        targets: tuple[ArtifactAttemptId, ...],
        transfer_deadline: datetime,
    ) -> ArtifactCleanupObligationDTO:
        if not self._session.in_transaction():
            raise RuntimeError("Original obligation creation requires its caller transaction.")
        if binding.kind is not ArtifactCleanupKind.ABANDONED_STAGING or len(targets) != 1:
            raise ArtifactReservationError("Staging creates only its exact original obligation.")
        # Share admission's queue turn before locking its original byte allocation.
        # This also protects direct trusted callers of the obligation capability.
        queue = await self._session.scalar(
            select(ApplicationJobQueueRow)
            .where(ApplicationJobQueueRow.singleton_key == 1)
            .with_for_update()
        )
        if queue is None:
            raise ArtifactReservationError("The shared allocation queue is unavailable.")
        existing = await self.get(binding.obligation_id)
        if existing is not None:
            if (
                existing.binding != binding
                or existing.targets != targets
                or existing.transfer_deadline != transfer_deadline
            ):
                raise ArtifactReservationError("The original obligation meaning cannot change.")
            return existing
        if isinstance(binding.origin, UnadmittedStagingArtifactOriginDTO) and targets != (
            binding.origin.attempt_id,
        ):
            raise ArtifactReservationError("Unadmitted staging belongs to its original attempt.")
        if isinstance(binding.origin, BusinessOperationArtifactOriginDTO):
            operation = await self._session.get(
                IdempotencyReservationRow, binding.origin.operation_id.value
            )
            if (
                operation is None
                or operation.organization_id != binding.scope.organization_id.value
                or operation.project_id != binding.scope.project_id.value
            ):
                raise ArtifactReservationError(
                    "The original business operation cannot be confirmed."
                )
            original_bytes = await self._session.scalar(
                select(
                    func.coalesce(func.sum(ArtifactStagingReservationRow.local_reserved_bytes), 0)
                )
                .join(
                    ArtifactCleanupTargetRow,
                    ArtifactCleanupTargetRow.attempt_id == ArtifactStagingReservationRow.attempt_id,
                )
                .join(
                    ArtifactCleanupObligationRow,
                    ArtifactCleanupObligationRow.id == ArtifactCleanupTargetRow.obligation_id,
                )
                .where(
                    ArtifactCleanupObligationRow.origin_operation_id
                    == binding.origin.operation_id.value
                )
            )
        else:
            original_bytes = 0
        target = targets[0]
        attempt = await self._session.get(ArtifactAttemptRow, target.value)
        reservation = await self._session.scalar(
            select(ArtifactStagingReservationRow)
            .where(ArtifactStagingReservationRow.attempt_id == target.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            attempt is None
            or reservation is None
            or reservation.expires_at != transfer_deadline
            or reservation.released
            or (attempt.installation_id, attempt.organization_id, attempt.project_id)
            != (
                binding.scope.installation_id.value,
                binding.scope.organization_id.value,
                binding.scope.project_id.value,
            )
        ):
            raise ArtifactReservationError("The original stage ownership cannot be confirmed.")
        original = await self._session.scalar(
            select(ArtifactCleanupObligationRow.id).where(
                ArtifactCleanupObligationRow.staging_reservation_id == reservation.id
            )
        )
        if original is not None:
            raise ArtifactReservationError(
                "The byte allocation already has its original staging obligation."
            )
        additional = reservation.local_reserved_bytes
        if (
            isinstance(binding.origin, BusinessOperationArtifactOriginDTO)
            and (original_bytes or 0) + additional > 256 * 1024 * 1024
        ):
            raise ArtifactCapacityError("The original job has no frozen spool capacity.")
        row = ArtifactCleanupObligationRow(
            id=binding.obligation_id.value,
            installation_id=binding.scope.installation_id.value,
            organization_id=binding.scope.organization_id.value,
            project_id=binding.scope.project_id.value,
            kind=binding.kind.value,
            staging_reservation_id=reservation.id,
            origin_kind="business"
            if isinstance(binding.origin, BusinessOperationArtifactOriginDTO)
            else "unadmitted_staging",
            request_id=binding.origin.request_id.value,
            transfer_deadline=transfer_deadline,
            origin_operation_id=binding.origin.operation_id.value
            if isinstance(binding.origin, BusinessOperationArtifactOriginDTO)
            else None,
            origin_attempt_id=binding.origin.attempt_id.value
            if isinstance(binding.origin, UnadmittedStagingArtifactOriginDTO)
            else None,
        )
        self._session.add(row)
        await self._session.flush()
        self._session.add_all(
            [
                ArtifactCleanupTargetRow(obligation_id=row.id, attempt_id=target.value)
                for target in targets
            ]
        )
        await self._session.flush()
        saved = await self.get(binding.obligation_id)
        if saved is None:
            raise ArtifactReservationError("The persisted original obligation disappeared.")
        return saved

    @override
    async def get(
        self, obligation_id: ArtifactCleanupObligationId
    ) -> ArtifactCleanupObligationDTO | None:
        row = await self._session.get(ArtifactCleanupObligationRow, obligation_id.value)
        if row is None:
            return None
        observed = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if observed is None:
            raise ArtifactReservationError("The original obligation clock is unavailable.")
        targets = tuple(
            ArtifactAttemptId(value)
            for value in await self._session.scalars(
                select(ArtifactCleanupTargetRow.attempt_id)
                .where(ArtifactCleanupTargetRow.obligation_id == row.id)
                .order_by(ArtifactCleanupTargetRow.attempt_id)
            )
        )
        job_id = await self._session.scalar(
            select(DurableJobRow.id).where(DurableJobRow.cleanup_obligation_id == row.id)
        )
        return ArtifactCleanupObligationDTO(
            binding=PostgresJobBindingMapper.cleanup(row),
            targets=targets,
            transfer_deadline=row.transfer_deadline,
            observed_at=observed,
            job_id=JobId(job_id) if job_id is not None else None,
            physically_complete=row.physically_complete,
            execution_status=JobStatus(row.execution_status)
            if row.execution_status is not None
            else None,
        )
