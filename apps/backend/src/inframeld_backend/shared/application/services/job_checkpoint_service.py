from typing import override

from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class JobCheckpointService(JobCheckpoints):
    """Commit protected progress or an honest stopped outcome, then close the stage."""

    def __init__(
        self,
        transactions: TransactionManager,
        jobs: JobStore,
        authorizer: AdmittedWorkAuthorizer,
        *,
        lease_seconds: float = 30,
    ) -> None:
        self._transactions = transactions
        self._jobs = jobs
        self._authorizer = authorizer
        self._lease_seconds = lease_seconds

    @override
    async def check(self, context: JobAttemptContextDTO) -> None:
        async with self._transactions.begin():
            current = await self._guard(context)
            if current is not None:
                await self._jobs.checkpoint(
                    context, current.checkpoint, lease_seconds=self._lease_seconds
                )
        self._require_continuation(current)

    @override
    async def save(self, context: JobAttemptContextDTO, data: bytes) -> None:
        async with self._transactions.begin():
            current = await self._guard(context)
            if current is not None:
                await self._jobs.checkpoint(context, data, lease_seconds=self._lease_seconds)
        self._require_continuation(current)

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        async with self._transactions.begin():
            current = await self._guard(context)
            if current is not None:
                await self._jobs.begin_effect(context, effect_id)
        self._require_continuation(current)

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        async with self._transactions.begin():
            current = await self._guard(context)
            if current is not None:
                await self._jobs.confirm_effect(context, effect_id, data)
        self._require_continuation(current)

    @override
    async def succeed(self, context: JobAttemptContextDTO) -> None:
        async with self._transactions.begin():
            current = await self._guard(context)
            if current is not None:
                await self._jobs.finish(context, status=JobStatus.SUCCEEDED, reason=None)
        self._require_continuation(current)
        if current is not None and current.pending_effect is not None:
            raise JobStoppedError("The job retained an unknown external outcome.")

    @override
    async def fail(self, context: JobAttemptContextDTO) -> None:
        async with self._transactions.begin():
            current = await self._guard(context)
            if current is not None:
                await self._jobs.finish(context, status=JobStatus.FAILED, reason="handler_failed")
        self._require_continuation(current)

    async def _guard(self, context: JobAttemptContextDTO) -> JobSnapshotDTO | None:
        try:
            await self._authorizer.require_current(context.authority)
        except AccessDeniedError:
            # Stopped metadata is safe to retain. No protected result is saved.
            await self._jobs.finish(context, status=JobStatus.FAILED, reason="authority_changed")
            return None
        current = await self._jobs.require_current(context)
        if current.cancel_requested:
            await self._jobs.finish(
                context, status=JobStatus.CANCELED, reason="cancellation_requested"
            )
            return None
        return current

    @staticmethod
    def _require_continuation(current: JobSnapshotDTO | None) -> None:
        if current is None:
            # Raise after transaction exit so the stopped outcome remains committed.
            raise JobStoppedError("The admitted work has stopped.")
