from typing import override

from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.project_deletion_job_facts_dto import (
    ProjectDeletionJobFactsDTO,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.project_deletion_job_authorizer import (
    ProjectDeletionJobAuthorizer,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.enums.job_status import JobStatus


class ProjectDeletionCheckpointService(JobCheckpoints):
    """Guard only local child execution using read-only original deletion proof.

    Parent completion and Access effects remain with the owning shutdown
    transaction. These checkpoints never mutate or settle that parent.
    """

    def __init__(
        self,
        transaction_manager: TransactionManager,
        job_store: JobStore,
        project_deletion_job_authorizer: ProjectDeletionJobAuthorizer,
        *,
        lease_seconds: float = 30,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._job_store = job_store
        self._project_deletion_job_authorizer = project_deletion_job_authorizer
        self._lease_seconds = lease_seconds

    @override
    async def check(self, context: JobAttemptContextDTO) -> None:
        async with self._transaction_manager.begin():
            _, current = await self._guard(context)
            await self._job_store.checkpoint(
                context, current.checkpoint, lease_seconds=self._lease_seconds
            )

    @override
    async def save(self, context: JobAttemptContextDTO, data: bytes) -> None:
        raise JobStoppedError("Deletion progress requires its owning shutdown transaction.")

    @override
    async def begin_effect(self, context: JobAttemptContextDTO, effect_id: str) -> None:
        raise JobStoppedError("Local Project shutdown cannot dispatch an external effect.")

    @override
    async def confirm_effect(
        self, context: JobAttemptContextDTO, effect_id: str, data: bytes
    ) -> None:
        raise JobStoppedError("Local Project shutdown cannot confirm an external effect.")

    @override
    async def succeed(self, context: JobAttemptContextDTO) -> None:
        async with self._transaction_manager.begin():
            facts, _ = await self._guard(context)
            if facts.shutdown_completed_at is None:
                raise JobStoppedError("The original local shutdown is not confirmed.")
            await self._job_store.finish(context, status=JobStatus.SUCCEEDED, reason=None)

    @override
    async def fail(self, context: JobAttemptContextDTO) -> None:
        async with self._transaction_manager.begin():
            await self._guard(context)
            await self._job_store.finish(context, status=JobStatus.FAILED, reason="handler_failed")

    async def _guard(
        self, context: JobAttemptContextDTO
    ) -> tuple[ProjectDeletionJobFactsDTO, JobSnapshotDTO]:
        """Read parent proof before child ownership, without taking a parent write lock.

        A shutdown-completed proof is monotonic. A later child terminal save
        cannot expire, reset or settle the parent physical-cleanup obligation.
        """
        if not isinstance(context.binding, ProjectDeletionJobBindingDTO):
            raise JobStoppedError("Deletion checkpoints require the original deletion binding.")

        facts = await self._project_deletion_job_authorizer.require_current(
            context.job_id, context.binding
        )
        if (
            facts.binding != context.binding
            or facts.job_id != context.job_id
            or facts.payload != context.payload
        ):
            raise ConflictError("Deletion backing changed the original child binding.")

        current = await self._job_store.require_current(context)
        if (
            current.job_id != context.job_id
            or current.binding != context.binding
            or current.payload != context.payload
        ):
            raise ConflictError("The current child changed its original deletion binding.")
        if current.pending_effect is not None:
            raise JobStoppedError("The local child retains an unexpected external outcome.")

        return facts, current
