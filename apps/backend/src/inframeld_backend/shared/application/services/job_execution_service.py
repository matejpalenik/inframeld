from dataclasses import replace
from uuid import UUID

from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.protocols.job_recovery import JobRecovery
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class JobExecutionService:
    """Coordinate original owner authority before the guarded queue turn."""

    def __init__(
        self,
        transactions: TransactionManager,
        jobs: JobStore,
        *,
        supported_payloads: tuple[tuple[str, int], ...],
        worker_id: UUID,
        product: AdmittedWorkAuthorizer,
        recovery: JobRecovery,
        lease_seconds: float = 30,
        work_seconds: float = 7200,
    ) -> None:
        self._transactions = transactions
        self._jobs = jobs
        self._supported_payloads = supported_payloads
        self._worker_id = worker_id
        self._lease_seconds = lease_seconds
        self._work_seconds = work_seconds
        self._product = product
        self._recovery = recovery

    async def claim_next(self) -> JobAttemptContextDTO | None:
        async with self._transactions.begin():
            observed = await self._jobs.peek_candidate()
            if observed is None:
                return None
            authority_changed = False
            if isinstance(observed.binding, ProductJobBindingDTO):
                try:
                    await self._product.require_current(observed.binding.authority)
                except AccessDeniedError:
                    authority_changed = True

            job = await self._jobs.next_candidate()
            if job is None:
                return None
            if replace(observed, observed_at=job.observed_at) != job:
                return None

            now = job.observed_at
            if job.status is JobStatus.RUNNING:
                if job.lease_expires_at is not None and job.lease_expires_at > now:
                    return None
                await self._recovery.recover_in_transaction(job)
                return None
            reason = None
            status = JobStatus.FAILED
            if authority_changed:
                reason = "authority_changed"
            elif job.cancel_requested:
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
