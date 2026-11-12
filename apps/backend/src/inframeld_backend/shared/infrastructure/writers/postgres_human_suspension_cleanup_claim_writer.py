from datetime import datetime, timedelta
from typing import override
from uuid import UUID, uuid4

from sqlalchemy import DateTime, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.protocols.human_suspension_cleanup_claim_writer import (
    HumanSuspensionCleanupClaimWriter,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.resources.postgres_recovery_worker_slot import (
    PostgresRecoveryWorkerSlot,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.readers.postgres_human_suspension_job_facts_reader import (
    PostgresHumanSuspensionJobFactsReader,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)


class PostgresHumanSuspensionCleanupClaimWriter(HumanSuspensionCleanupClaimWriter):
    """Claim the next eligible suspension cleanup in the caller's transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
    ) -> None:
        self._session = session
        self._installation_id = installation_id
        self._authority = authority

    @override
    async def claim_next(
        self, *, worker_id: UUID, lease_seconds: float, work_seconds: float
    ) -> JobAttemptContextDTO | None:
        """Take one shared slot or settle one expired or otherwise stopped original."""
        if (
            isinstance(lease_seconds, bool)
            or isinstance(work_seconds, bool)
            or not 0 < lease_seconds <= 120
            or not 0 < work_seconds <= 7200
        ):
            raise ValueError("The suspension attempt budget is outside its finite bounds.")

        slot = PostgresRecoveryWorkerSlot(self._session)
        observed_at = await slot.acquire_if_free(self._installation_id)
        if observed_at is None:
            return None
        with self._session.no_autoflush:
            candidate = await self._candidate(observed_at)
            if candidate is None:
                return None
            binding = PostgresJobBindingMapper.human_suspension(candidate)
            facts = PostgresHumanSuspensionJobFactsReader(self._session)
            parent = await facts.lock_original(binding)
            if parent is None:
                return None
            job = await facts.lock_child(parent)
            if job is None:
                raise ConflictError("The exact suspension cleanup job is unavailable.")
            current = await facts.has_current_target(binding)
            now = await self._now()
            first = await self._candidate(now)
            if first is None or first.id != parent.id:
                return None
            repeat = (
                job.pending_effect is not None
                and await facts.lock_unused_repeat(parent, job) is not None
            )
            now = await self._now()

            if job.status == JobStatus.RUNNING.value:
                await self._retire_expired(parent, job, current=current, repeat=repeat)
                return None
            if job.status != JobStatus.QUEUED.value:
                return None
            if (
                job.worker_id is not None
                or job.fence is not None
                or job.lease_expires_at is not None
                or job.attempt_count < 0
                or (job.attempt_count == 0) != (job.work_deadline is None)
            ):
                raise ConflictError("The queued suspension attempt history is inconsistent.")

            stopped = self._stopped(job, now=now, current=current, repeat=repeat)
            if stopped is not None:
                self._settle(parent, job, now=now, status=stopped[0], reason=stopped[1])
                await self._session.flush()
                return None
            if now < job.admitted_at or job.due_at > now:
                return None
            if job.attempt_count:
                previous = await self._session.get(
                    DurableJobAttemptRow, (job.id, job.attempt_count)
                )
                if previous is None or previous.ended_at is None:
                    raise ConflictError("The previous suspension attempt is still unresolved.")

            deadline = job.work_deadline or now + timedelta(seconds=work_seconds)
            fence = JobFence(uuid4())
            job.status = JobStatus.RUNNING.value
            job.attempt_count += 1
            job.worker_id = worker_id
            job.fence = fence.value
            job.work_deadline = deadline
            job.lease_expires_at = min(now + timedelta(seconds=lease_seconds), deadline)
            job.reason = None
            self._session.add(
                DurableJobAttemptRow(
                    job_id=job.id,
                    number=job.attempt_count,
                    fence=fence.value,
                    worker_id=worker_id,
                    started_at=now,
                )
            )
            await self._session.flush()
            return JobAttemptContextDTO(
                job_id=binding.job_id,
                binding=binding,
                payload=JobPayload(job.payload_kind, job.payload_version, job.payload),
                attempt=job.attempt_count,
                fence=fence,
                work_deadline=deadline,
                checkpoint=job.checkpoint,
            )

    async def _candidate(self, now: datetime) -> HumanSuspensionObligationRow | None:
        parent, job = HumanSuspensionObligationRow, DurableJobRow
        return await self._session.scalar(
            select(parent)
            .join(job, job.suspension_obligation_id == parent.id)
            .where(
                parent.installation_id == self._installation_id.value,
                parent.authority == self._authority.value,
                parent.completed_at.is_(None),
                parent.queue_exhausted_at.is_(None),
                job.binding_kind == "human_suspension",
                or_(
                    and_(
                        job.status == JobStatus.QUEUED.value,
                        or_(
                            job.due_at <= now, job.queued_deadline <= now, job.work_deadline <= now
                        ),
                    ),
                    and_(
                        job.status == JobStatus.RUNNING.value,
                        job.lease_expires_at <= now,
                    ),
                ),
            )
            .order_by(parent.admitted_at, parent.job_id)
            .limit(1)
            .execution_options(populate_existing=True)
        )

    async def _retire_expired(
        self,
        parent: HumanSuspensionObligationRow,
        job: DurableJobRow,
        *,
        current: bool,
        repeat: bool,
    ) -> None:
        attempt = await self._session.get(
            DurableJobAttemptRow,
            (job.id, job.attempt_count),
            populate_existing=True,
            with_for_update=True,
        )
        if (
            attempt is None
            or attempt.ended_at is not None
            or attempt.worker_id != job.worker_id
            or attempt.fence != job.fence
            or not 1 <= job.attempt_count <= 3
            or job.lease_expires_at is None
            or job.work_deadline is None
            or not parent.admitted_at <= attempt.started_at < parent.queued_deadline
            or not attempt.started_at <= job.lease_expires_at <= job.work_deadline
        ):
            raise ConflictError("The expired suspension attempt cannot be reconciled.")
        now = await self._now()
        if job.lease_expires_at > now:
            return

        stopped = self._stopped(job, now=now, current=current, repeat=repeat)
        status, reason = stopped or (JobStatus.QUEUED, "lease_expired_without_pending_effect")
        attempt.ended_at, attempt.reason = now, reason
        if status is JobStatus.QUEUED:
            job.due_at = now + timedelta(seconds=min(5 * job.attempt_count, 15))
        self._settle(parent, job, now=now, status=status, reason=reason)
        await self._session.flush()

    @staticmethod
    def _stopped(
        job: DurableJobRow, *, now: datetime, current: bool, repeat: bool
    ) -> tuple[JobStatus, str] | None:
        if job.pending_effect is not None and not repeat:
            return JobStatus.RECOVERY_REQUIRED, "provider_outcome_uncertain"
        if not current:
            return JobStatus.FAILED, "original_suspension_not_current"
        if job.cancel_requested:
            return JobStatus.CANCELED, "cancellation_requested"
        if job.queued_deadline <= now:
            return JobStatus.FAILED, "queue_wait_exhausted"
        if job.work_deadline is not None and job.work_deadline <= now:
            return JobStatus.FAILED, "work_deadline_exhausted"
        if job.attempt_count >= 3:
            return JobStatus.FAILED, "attempt_budget_exhausted"
        return None

    @staticmethod
    def _settle(
        parent: HumanSuspensionObligationRow,
        job: DurableJobRow,
        *,
        now: datetime,
        status: JobStatus,
        reason: str,
    ) -> None:
        if now >= parent.queued_deadline:
            parent.queue_exhausted_at = now
        job.status, job.reason = status.value, reason
        job.terminal_at = None if status is JobStatus.QUEUED else now
        job.worker_id = job.fence = job.lease_expires_at = None

    async def _now(self) -> datetime:
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise DependencyUnavailableError("The authoritative database clock is unavailable.")
        return now
