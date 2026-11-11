import asyncio
from typing import override

from inframeld_backend.access.application.dtos.project_deletion_shutdown_facts_dto import (
    ProjectDeletionShutdownFactsDTO,
)
from inframeld_backend.access.application.protocols.project_application_shutdown_effects_writer import (
    ProjectApplicationShutdownEffectsWriter,
)
from inframeld_backend.access.application.protocols.project_deletion_shutdown import (
    ProjectDeletionShutdown,
)
from inframeld_backend.access.application.protocols.project_deletion_shutdown_writer import (
    ProjectDeletionShutdownWriter,
)
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.protocols.job_store import JobStore
from inframeld_backend.shared.application.protocols.project_deletion_job_authorizer import (
    ProjectDeletionJobAuthorizer,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectDeletionShutdownService(ProjectDeletionShutdown):
    """Coordinate genuine original backing, local application effects and their checkpoint."""

    def __init__(
        self,
        *,
        transaction_manager: TransactionManager,
        project_deletion_shutdown_writer: ProjectDeletionShutdownWriter,
        project_deletion_job_authorizer: ProjectDeletionJobAuthorizer,
        job_store: JobStore,
        application_shutdown_effects_writer: ProjectApplicationShutdownEffectsWriter,
    ) -> None:
        self._transaction_manager = transaction_manager
        self._project_deletion_shutdown_writer = project_deletion_shutdown_writer
        self._project_deletion_job_authorizer = project_deletion_job_authorizer
        self._job_store = job_store
        self._application_shutdown_effects_writer = application_shutdown_effects_writer

    @override
    async def shutdown(self, context: JobAttemptContextDTO) -> None:
        binding = context.binding
        if not isinstance(binding, ProjectDeletionJobBindingDTO) or (
            context.payload.kind,
            context.payload.version,
            context.payload.data,
        ) != ("project.application-shutdown", 1, binding.obligation_id.bytes):
            raise JobStoppedError("The child does not match original Project shutdown work.")

        try:
            async with asyncio.timeout(5), self._transaction_manager.begin():
                facts = await self._project_deletion_shutdown_writer.lock_original(context)
                self._require_locked_scope(facts, binding)
                backing = await self._project_deletion_job_authorizer.require_current(
                    context.job_id, binding
                )
                if (
                    backing.binding != binding
                    or backing.job_id != context.job_id
                    or backing.payload != context.payload
                ):
                    raise RuntimeError("The backing changed the original shutdown binding.")
                if (
                    backing.source_revision != facts.source_revision
                    or backing.shutdown_completed_at != facts.shutdown_completed_at
                ):
                    raise ConflictError("The original shutdown checkpoint observations disagree.")

                await self._require_current_child(context)
                if facts.shutdown_completed_at is not None:
                    return

                changed = await self._application_shutdown_effects_writer.shutdown(
                    installation_id=facts.installation_id,
                    organization_id=facts.organization_id,
                    project_id=facts.project_id,
                )
                if type(changed) is not bool:
                    raise RuntimeError(
                        "Application shutdown returned no checked local change result."
                    )
                if changed and facts.access_revision == RevisionValidation.MAX_VALUE:
                    raise ConflictError("The Project Access revision cannot advance.")

                # Locks do not stop time. Confirm the original live fence again
                # after account/key waits, before recording protected progress.
                await self._require_current_child(context)
                await self._project_deletion_shutdown_writer.record_shutdown(
                    context,
                    facts=facts,
                    changed=changed,
                    access_revision=facts.access_revision + int(changed),
                )
        except TimeoutError:
            raise DependencyUnavailableError() from None

    @staticmethod
    def _require_locked_scope(
        facts: ProjectDeletionShutdownFactsDTO, binding: ProjectDeletionJobBindingDTO
    ) -> None:
        """Match actual locked Project observations before treating retained backing as usable."""
        if facts.binding != binding or (
            facts.installation_id,
            facts.organization_id.value,
            facts.project_id.value,
        ) != (
            binding.installation_id,
            binding.organization_id,
            binding.project_id,
        ):
            raise RuntimeError("The locked shutdown scope or original binding changed.")

        if facts.project_status is not ProjectStatus.DELETING:
            raise ConflictError("The Project is not in its admitted deletion lifecycle.")
        if (
            type(facts.access_revision) is not int
            or not binding.access_revision <= facts.access_revision <= RevisionValidation.MAX_VALUE
        ):
            raise ConflictError("The locked Project Access revision is incoherent.")

    async def _require_current_child(self, context: JobAttemptContextDTO) -> None:
        """Keep live ownership and original deadlines with the existing job store."""
        current = await self._job_store.require_current(context)
        if (
            current.job_id != context.job_id
            or current.binding != context.binding
            or current.payload != context.payload
            or current.attempt != context.attempt
            or current.fence != context.fence
            or current.work_deadline != context.work_deadline
            or current.status is not JobStatus.RUNNING
        ):
            raise JobFenceLostError("The current child changed its original shutdown ownership.")
        if current.pending_effect is not None:
            raise JobStoppedError("The local child retains an unexpected external outcome.")
