from datetime import datetime, timedelta
from typing import override
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.enums.job_status import JobStatus
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import JobQueueFullError
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


class PostgresJobStore(JobStore):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def admit(
        self,
        *,
        operation_id: OperationId,
        request_id: RequestId,
        authority: AdmittedWorkAuthorityDTO,
        payload: JobPayload,
        capacity: int,
    ) -> JobAdmissionDTO:
        if not self._session.in_transaction():
            raise RuntimeError("Job admission requires its caller-owned transaction.")
        if not 1 <= capacity <= 8:
            raise ValueError("Ordinary job capacity must be between one and eight.")
        queue = await self._session.scalar(
            select(ApplicationJobQueueRow)
            .where(ApplicationJobQueueRow.singleton_key == 1)
            .with_for_update()
        )
        if queue is None:
            raise RuntimeError("The ordinary job queue is not initialized.")

        reservation = await self._session.scalar(
            select(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == operation_id.value
            )
        )
        if reservation is None or (
            reservation.state is not OperationReservationState.IN_PROGRESS
            or reservation.principal_id != authority.principal_id.value
            or reservation.organization_id != authority.organization_id.value
            or reservation.project_id != authority.project_id.value
        ):
            raise ConflictError("Job admission requires its original checked reservation.")
        count = await self._session.scalar(
            select(func.count())
            .select_from(DurableJobRow)
            .where(DurableJobRow.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value)))
        )
        if count is None or count >= capacity:
            raise JobQueueFullError("The ordinary job queue is full.")
        now = await self._session.scalar(select(func.clock_timestamp()))
        if now is None:
            raise RuntimeError("The database clock is unavailable.")
        job_id = JobId(uuid4())
        binding = authority.human_binding
        self._session.add(
            DurableJobRow(
                id=job_id.value,
                operation_id=operation_id.value,
                request_id=request_id.value,
                installation_id=authority.installation_id.value,
                principal_id=authority.principal_id.value,
                principal_kind=authority.principal_kind.value,
                organization_id=authority.organization_id.value,
                project_id=authority.project_id.value,
                action_id=authority.action_id.value,
                payload_kind=payload.kind,
                payload_version=payload.version,
                payload=payload.data,
                admitted_at=now,
                queued_deadline=now + timedelta(hours=24),
                due_at=now,
                human_authority=binding.identity.authority.value if binding is not None else None,
                human_subject=binding.identity.subject.value if binding is not None else None,
                human_version=binding.version.value if binding is not None else None,
            )
        )
        await self._session.flush()
        return JobAdmissionDTO(job_id, operation_id, True)

    @override
    async def find(self, operation_id: OperationId) -> JobSnapshotDTO | None:
        raise NotImplementedError

    @override
    async def next_candidate(self) -> JobSnapshotDTO | None:
        raise NotImplementedError

    @override
    async def start_attempt(
        self, job: JobSnapshotDTO, *, worker_id: UUID, lease_seconds: float, work_seconds: float
    ) -> JobAttemptContextDTO:
        raise NotImplementedError

    @override
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO:
        raise NotImplementedError

    @override
    async def checkpoint(
        self, context: JobAttemptContextDTO, data: bytes, *, lease_seconds: float
    ) -> None:
        raise NotImplementedError

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        raise NotImplementedError

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        raise NotImplementedError

    @override
    async def finish(
        self, context: JobAttemptContextDTO, *, status: JobStatus, reason: str | None
    ) -> None:
        raise NotImplementedError

    @override
    async def retire_attempt(
        self, job: JobSnapshotDTO, *, status: JobStatus, reason: str, due_at: datetime
    ) -> None:
        raise NotImplementedError

    @override
    async def request_cancel(self, job_id: JobId) -> None:
        raise NotImplementedError
