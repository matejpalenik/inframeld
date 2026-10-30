from datetime import timedelta
from uuid import UUID

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.policies.job_retry_policy import JobRetryPolicy


class JobExecutionService:
    """Choose one supported eligible attempt under durable queue coordination."""

    def __init__(
        self,
        transactions: TransactionManager,
        jobs: JobStore,
        *,
        supported_payloads: tuple[tuple[str, int], ...],
        worker_id: UUID,
        lease_seconds: float = 30,
        work_seconds: float = 7200,
    ) -> None:
        self._transactions = transactions
        self._jobs = jobs
        self._supported_payloads = supported_payloads
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._work_seconds = work_seconds

    async def claim_next(self) -> JobAttemptContextDTO | None:
        async with self._transactions.begin():
            job = await self._jobs.next_candidate()
            if job is None:
                return None
            now = job.observed_at
            if job.status is JobStatus.RUNNING:
                if job.lease_expires_at is not None and job.lease_expires_at > now:
                    return None
                status = JobRetryPolicy.after_interruption(
                    attempt=job.attempt,
                    uncertain_effect=job.pending_effect is not None,
                    deadline_expired=job.work_deadline is None or job.work_deadline <= now,
                )
                reason = (
                    "unknown_external_effect"
                    if status is JobStatus.RECOVERY_REQUIRED
                    else "attempt_budget_exhausted"
                    if status is JobStatus.FAILED
                    else "lease_lost_safe_retry"
                )
                await self._jobs.retire_attempt(
                    job,
                    status=status,
                    reason=reason,
                    due_at=now + timedelta(seconds=min(5 * job.attempt, 15)),
                )
                return None
            reason = None
            status = JobStatus.FAILED
            if job.cancel_requested:
                status, reason = JobStatus.CANCELED, "cancellation_requested"
            elif job.queued_deadline <= now:
                reason = "queue_wait_exhausted"
            elif job.work_deadline is not None and job.work_deadline <= now:
                reason = "work_deadline_exhausted"
            elif (job.payload.kind, job.payload.version) not in self._supported_payloads:
                reason = "unsupported_payload"
            if reason is not None:
                await self._jobs.retire_attempt(job, status=status, reason=reason, due_at=now)
                return None
            return await self._jobs.start_attempt(
                job,
                worker_id=self._worker_id,
                lease_seconds=self._lease_seconds,
                work_seconds=self._work_seconds,
            )
