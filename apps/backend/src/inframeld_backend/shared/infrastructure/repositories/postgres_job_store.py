from datetime import datetime, timedelta
from typing import override
from uuid import UUID, uuid4

from sqlalchemy import DateTime, case, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.job_admission_dto import JobAdmissionDTO
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobQueueFullError,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
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
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(DurableJobRow.operation_id == operation_id.value)
            .execution_options(populate_existing=True)
        )
        return None if row is None else self._snapshot(row, await self._now())

    @override
    async def next_candidate(self) -> JobSnapshotDTO | None:
        await self._queue_turn()
        now = await self._now()
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(
                or_(
                    DurableJobRow.status == JobStatus.RUNNING.value,
                    (DurableJobRow.status == JobStatus.QUEUED.value)
                    & or_(DurableJobRow.due_at <= now, DurableJobRow.queued_deadline <= now),
                )
            )
            .order_by(
                case((DurableJobRow.status == JobStatus.RUNNING.value, 0), else_=1),
                DurableJobRow.admitted_at,
                DurableJobRow.id,
            )
            .limit(1)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return None if row is None else self._snapshot(row, now)

    @override
    async def start_attempt(
        self, job: JobSnapshotDTO, *, worker_id: UUID, lease_seconds: float, work_seconds: float
    ) -> JobAttemptContextDTO:
        await self._queue_turn()
        if not 0 < lease_seconds <= 120 or not 0 < work_seconds <= 7200:
            raise ValueError("The ordinary attempt budget is outside its finite bounds.")
        now = await self._now()
        active = await self._session.scalar(
            select(func.count())
            .select_from(DurableJobRow)
            .where(DurableJobRow.status == JobStatus.RUNNING.value)
        )
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(DurableJobRow.id == job.job_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            active
            or row is None
            or row.status != JobStatus.QUEUED.value
            or row.cancel_requested
            or row.due_at > now
            or row.queued_deadline <= now
            or row.attempt_count >= 3
        ):
            raise ConflictError("The job is not eligible for a new attempt.")
        deadline = row.work_deadline or now + timedelta(seconds=work_seconds)
        if deadline <= now:
            raise ConflictError("The original job work deadline has expired.")
        fence = JobFence(uuid4())
        row.status = JobStatus.RUNNING.value
        row.attempt_count += 1
        row.fence = fence.value
        row.worker_id = worker_id
        row.work_deadline = deadline
        row.lease_expires_at = min(now + timedelta(seconds=lease_seconds), deadline)
        self._session.add(
            DurableJobAttemptRow(
                job_id=row.id,
                number=row.attempt_count,
                fence=fence.value,
                worker_id=worker_id,
                started_at=now,
            )
        )
        await self._session.flush()
        saved = self._snapshot(row, now)
        return JobAttemptContextDTO(
            saved.job_id,
            saved.operation_id,
            saved.request_id,
            saved.authority,
            saved.payload,
            saved.attempt,
            fence,
            deadline,
            saved.checkpoint,
        )

    @override
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO:
        row, now = await self._owned_row(context)
        return self._snapshot(row, now)

    @override
    async def checkpoint(
        self, context: JobAttemptContextDTO, data: bytes, *, lease_seconds: float
    ) -> None:
        self._require_checkpoint(data)
        if not 0 < lease_seconds <= 120:
            raise ValueError("The lease is outside its bounded interval.")
        row, now = await self._owned_row(context)
        if row.work_deadline is None:
            raise JobFenceLostError()
        row.checkpoint = data
        row.lease_expires_at = min(now + timedelta(seconds=lease_seconds), row.work_deadline)
        await self._session.flush()

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        if not effect_id or len(effect_id) > 100:
            raise ValueError("An effect requires a bounded stable unit identifier.")
        row, _ = await self._owned_row(context)
        if row.pending_effect is not None:
            raise ConflictError("An earlier effect still has an unknown outcome.")
        row.pending_effect = effect_id
        await self._session.flush()

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        self._require_checkpoint(data)
        row, _ = await self._owned_row(context)
        if row.pending_effect != effect_id:
            raise ConflictError("The confirmation does not match the original pending effect.")
        row.pending_effect = None
        row.checkpoint = data
        await self._session.flush()

    @override
    async def finish(
        self, context: JobAttemptContextDTO, *, status: JobStatus, reason: str | None
    ) -> None:
        row, now = await self._owned_row(context)
        if status in (JobStatus.QUEUED, JobStatus.RUNNING):
            raise ValueError("Finishing requires a terminal execution outcome.")
        if row.pending_effect is not None:
            status, reason = JobStatus.RECOVERY_REQUIRED, "unknown_external_effect"
        await self._complete(row, now, status, reason)

    @override
    async def retire_attempt(
        self, job: JobSnapshotDTO, *, status: JobStatus, reason: str, due_at: datetime
    ) -> None:
        await self._queue_turn()
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(DurableJobRow.id == job.job_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            row is None
            or job.status not in (JobStatus.QUEUED, JobStatus.RUNNING)
            or row.status != job.status.value
            or row.attempt_count != job.attempt
            or row.fence != (job.fence.value if job.fence is not None else None)
        ):
            raise JobFenceLostError()
        now = await self._now()
        if (
            row.status == JobStatus.RUNNING.value
            and row.lease_expires_at is not None
            and row.lease_expires_at > now
        ):
            raise JobFenceLostError("An unexpired owner cannot be retired by another worker.")
        if status is JobStatus.QUEUED:
            if row.pending_effect is not None or row.attempt_count >= 3:
                raise ConflictError("The original remaining work cannot safely retry.")
            await self._end_attempt(row, now, reason)
            row.status, row.reason, row.due_at = status.value, reason, due_at
            row.fence = row.worker_id = row.lease_expires_at = None
            await self._session.flush()
        elif status is not JobStatus.RUNNING:
            await self._complete(row, now, status, reason)
        else:
            raise ValueError("Retirement cannot start an attempt.")

    @override
    async def request_cancel(self, job_id: JobId) -> None:
        self._require_transaction()
        await self._session.execute(
            update(DurableJobRow)
            .where(
                DurableJobRow.id == job_id.value,
                DurableJobRow.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value)),
            )
            .values(cancel_requested=True)
        )

    def _require_transaction(self) -> None:
        if not self._session.in_transaction():
            raise RuntimeError("Job persistence requires its caller-owned transaction.")

    async def _queue_turn(self) -> None:
        self._require_transaction()
        row = await self._session.scalar(
            select(ApplicationJobQueueRow)
            .where(ApplicationJobQueueRow.singleton_key == 1)
            .with_for_update()
        )
        if row is None:
            raise RuntimeError("The ordinary queue is not initialized.")

    async def _now(self) -> datetime:
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise RuntimeError("The authoritative database clock is unavailable.")
        return now

    async def _owned_row(self, context: JobAttemptContextDTO) -> tuple[DurableJobRow, datetime]:
        self._require_transaction()
        row = await self._session.scalar(
            select(DurableJobRow)
            .where(
                DurableJobRow.id == context.job_id.value,
                DurableJobRow.status == JobStatus.RUNNING.value,
                DurableJobRow.fence == context.fence.value,
                DurableJobRow.attempt_count == context.attempt,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        now = await self._now()
        if (
            row is None
            or row.lease_expires_at is None
            or row.lease_expires_at <= now
            or row.work_deadline is None
            or row.work_deadline <= now
        ):
            raise JobFenceLostError("The ordinary job attempt no longer owns its lease.")
        saved = self._snapshot(row, now)
        if (
            saved.operation_id != context.operation_id
            or saved.request_id != context.request_id
            or saved.authority != context.authority
            or saved.payload != context.payload
        ):
            raise JobFenceLostError("The attempt does not match its original immutable work.")
        return row, now

    @staticmethod
    def _require_checkpoint(data: bytes) -> None:
        if len(data) > 65536:
            raise ValueError("A job checkpoint may contain at most 64 KiB.")

    async def _end_attempt(self, row: DurableJobRow, now: datetime, reason: str | None) -> None:
        if row.fence is not None:
            await self._session.execute(
                update(DurableJobAttemptRow)
                .where(
                    DurableJobAttemptRow.job_id == row.id,
                    DurableJobAttemptRow.fence == row.fence,
                    DurableJobAttemptRow.ended_at.is_(None),
                )
                .values(ended_at=now, reason=reason)
            )

    async def _complete(
        self, row: DurableJobRow, now: datetime, status: JobStatus, reason: str | None
    ) -> None:
        if reason is not None and len(reason) > 100:
            raise ValueError("A job outcome reason must be bounded.")
        await self._end_attempt(row, now, reason)
        row.status, row.reason, row.terminal_at = status.value, reason, now
        row.fence = row.worker_id = row.lease_expires_at = None
        await self._session.execute(
            update(IdempotencyReservationRow)
            .where(
                IdempotencyReservationRow.operation_id == row.operation_id,
                IdempotencyReservationRow.state == OperationReservationState.REPLAYABLE,
                IdempotencyReservationRow.replay_kind == OperationReplayKind.ASYNC_JOB,
                IdempotencyReservationRow.expires_at.is_(None),
            )
            .values(expires_at=now + timedelta(hours=24))
        )
        await self._session.flush()

    @staticmethod
    def _snapshot(row: DurableJobRow, now: datetime) -> JobSnapshotDTO:
        binding = None
        if (
            row.human_authority is not None
            or row.human_subject is not None
            or row.human_version is not None
        ):
            if (
                row.human_authority is None
                or row.human_subject is None
                or row.human_version is None
            ):
                raise ConflictError("The original human security generation is incomplete.")
            binding = HumanOAuthCredentialBindingDTO(
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(row.human_authority), IdentitySubject(row.human_subject)
                ),
                InstallationId(row.installation_id),
                HumanCredentialVersion(row.human_version),
            )
        authority = AdmittedWorkAuthorityDTO(
            PrincipalId(row.principal_id),
            PrincipalKind(row.principal_kind),
            InstallationId(row.installation_id),
            OrganizationId(row.organization_id),
            ProjectId(row.project_id),
            ActionId(row.action_id),
            binding,
        )
        return JobSnapshotDTO(
            JobId(row.id),
            OperationId(row.operation_id),
            RequestId(row.request_id),
            authority,
            JobPayload(row.payload_kind, row.payload_version, row.payload),
            JobStatus(row.status),
            row.admitted_at,
            row.queued_deadline,
            row.due_at,
            now,
            row.attempt_count,
            row.work_deadline,
            JobFence(row.fence) if row.fence is not None else None,
            row.lease_expires_at,
            row.cancel_requested,
            row.pending_effect,
            row.reason,
            row.checkpoint,
        )
