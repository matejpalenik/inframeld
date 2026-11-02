from datetime import timedelta
from typing import override
from uuid import uuid4

from sqlalchemy import DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.artifact_cleanup_admission_dto import (
    ArtifactCleanupAdmissionDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.errors.artifact_errors import ArtifactReservationError
from inframeld_backend.shared.application.errors.job_errors import JobQueueFullError
from inframeld_backend.shared.application.protocols.artifact_cleanup_admission_writer import (
    ArtifactCleanupAdmissionWriter,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_target_row import (
    ArtifactCleanupTargetRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow


class PostgresArtifactCleanupAdmissionWriter(ArtifactCleanupAdmissionWriter):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def admit(
        self, binding: ArtifactCleanupJobBindingDTO, *, capacity: int = 8
    ) -> ArtifactCleanupAdmissionDTO:
        if not self._session.in_transaction():
            raise RuntimeError("Cleanup admission requires its caller transaction.")
        if type(capacity) is not int or not 1 <= capacity <= 8:
            raise ValueError("The application queue capacity must be between one and eight.")
        queue = await self._session.scalar(
            select(ApplicationJobQueueRow)
            .where(ApplicationJobQueueRow.singleton_key == 1)
            .with_for_update()
        )
        if queue is None:
            raise ArtifactReservationError("The shared queue is unavailable.")
        existing = await self._session.scalar(
            select(DurableJobRow).where(
                DurableJobRow.cleanup_obligation_id == binding.obligation_id.value
            )
        )
        obligation = await self._session.scalar(
            select(ArtifactCleanupObligationRow)
            .where(ArtifactCleanupObligationRow.id == binding.obligation_id.value)
            .with_for_update()
        )
        if obligation is None or PostgresJobBindingMapper.cleanup(obligation) != binding:
            raise ArtifactReservationError("The original obligation meaning cannot be confirmed.")
        if existing is not None:
            if existing.binding_kind != "artifact_cleanup" or (
                existing.installation_id,
                existing.organization_id,
                existing.project_id,
            ) != (
                binding.scope.installation_id.value,
                binding.scope.organization_id.value,
                binding.scope.project_id.value,
            ):
                raise ArtifactReservationError("The original cleanup job binding is inconsistent.")
            return ArtifactCleanupAdmissionDTO(JobId(existing.id), binding.obligation_id, False)
        count = await self._session.scalar(
            select(func.count())
            .select_from(DurableJobRow)
            .where(DurableJobRow.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value)))
        )
        if count is None or count >= capacity:
            raise JobQueueFullError()
        targets = await self._session.scalar(
            select(func.count())
            .select_from(ArtifactCleanupTargetRow)
            .where(ArtifactCleanupTargetRow.obligation_id == obligation.id)
        )
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if (
            not targets
            or now is None
            or not now < obligation.transfer_deadline <= now + timedelta(hours=2)
        ):
            raise ArtifactReservationError(
                "The original bounded cleanup allocation cannot be confirmed."
            )
        job_id = JobId(uuid4())
        self._session.add(
            DurableJobRow(
                id=job_id.value,
                operation_id=None,
                request_id=binding.origin.request_id.value,
                installation_id=binding.scope.installation_id.value,
                principal_id=None,
                principal_kind=None,
                organization_id=binding.scope.organization_id.value,
                project_id=binding.scope.project_id.value,
                action_id=None,
                payload_kind="artifact.cleanup",
                payload_version=1,
                payload=binding.obligation_id.value.bytes,
                admitted_at=now,
                queued_deadline=now + timedelta(hours=24),
                due_at=obligation.transfer_deadline,
                binding_kind="artifact_cleanup",
                cleanup_obligation_id=obligation.id,
            )
        )
        await self._session.flush()
        return ArtifactCleanupAdmissionDTO(job_id, binding.obligation_id, True)
