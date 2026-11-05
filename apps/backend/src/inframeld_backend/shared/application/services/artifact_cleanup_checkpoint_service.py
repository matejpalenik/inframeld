from typing import override

from inframeld_backend.shared.application.dtos.artifact_cleanup_facts_dto import (
    ArtifactCleanupFactsDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.errors.application_errors import AccessDeniedError
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.artifact_cleanup_authorizer import (
    ArtifactCleanupAuthorizer,
)
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class ArtifactCleanupCheckpointService(JobCheckpoints):
    """Guard cleanup steps with the original obligation and live immutable fence."""

    def __init__(
        self,
        transaction_manager: TransactionManager,
        job_store: JobStore,
        artifact_cleanup_authorizer: ArtifactCleanupAuthorizer,
        *,
        lease_seconds: float = 30,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._job_store = job_store
        self._artifact_cleanup_authorizer = artifact_cleanup_authorizer
        self._lease_seconds = lease_seconds

    @override
    async def check(self, context: JobAttemptContextDTO) -> None:
        async with self._transaction_manager.begin():
            current = await self._guard(context)
            if current is not None:
                await self._job_store.checkpoint(
                    context, current[0].checkpoint, lease_seconds=self._lease_seconds
                )
        self._require_continuation(current)

    @override
    async def save(self, context: JobAttemptContextDTO, data: bytes) -> None:
        async with self._transaction_manager.begin():
            current = await self._guard(context)
            if current is not None:
                await self._job_store.checkpoint(context, data, lease_seconds=self._lease_seconds)
        self._require_continuation(current)

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        async with self._transaction_manager.begin():
            current = await self._guard(context)
            if current is not None:
                await self._job_store.begin_effect(context, effect_id)
        self._require_continuation(current)

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        async with self._transaction_manager.begin():
            current = await self._guard(context)
            if current is not None:
                await self._job_store.confirm_effect(context, effect_id, data)
        self._require_continuation(current)

    @override
    async def succeed(self, context: JobAttemptContextDTO) -> None:
        async with self._transaction_manager.begin():
            current = await self._guard(context)
            if current is not None:
                await self._job_store.finish(
                    context,
                    status=JobStatus.SUCCEEDED
                    if current[1].physically_complete
                    else JobStatus.RECOVERY_REQUIRED,
                    reason=None if current[1].physically_complete else "physical_cleanup_pending",
                )
        self._require_continuation(current)
        if current is not None and (
            not current[1].physically_complete or current[0].pending_effect is not None
        ):
            raise JobStoppedError("The original physical cleanup remains pending.")

    @override
    async def fail(self, context: JobAttemptContextDTO) -> None:
        async with self._transaction_manager.begin():
            current = await self._guard(context)
            if current is not None:
                await self._job_store.finish(
                    context, status=JobStatus.FAILED, reason="cleanup_handler_failed"
                )
        self._require_continuation(current)

    async def _guard(
        self, context: JobAttemptContextDTO
    ) -> tuple[JobSnapshotDTO, ArtifactCleanupFactsDTO] | None:
        """Check current cleanup ownership and authority before another storage effect."""
        if not isinstance(context.binding, ArtifactCleanupJobBindingDTO):
            raise JobStoppedError("Cleanup checkpoints require the original cleanup binding.")
        # Lock the live job before its obligation and exact target rows. No
        # product principal, Project status or grant can replace this authority.
        current = await self._job_store.require_current(context)
        try:
            facts = await self._artifact_cleanup_authorizer.require_current(
                context.job_id, context.binding
            )
        except AccessDeniedError:
            await self._job_store.finish(
                context, status=JobStatus.FAILED, reason="cleanup_authority_changed"
            )
            return None
        return current, facts

    @staticmethod
    def _require_continuation(
        current: tuple[JobSnapshotDTO, ArtifactCleanupFactsDTO] | None,
    ) -> None:
        """Reject cleanup work whose checked continuation is no longer valid."""
        if current is None:
            raise JobStoppedError("The original cleanup authority cannot be confirmed.")
