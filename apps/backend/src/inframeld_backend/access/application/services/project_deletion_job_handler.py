from typing import override

from inframeld_backend.access.application.protocols.project_deletion_shutdown import (
    ProjectDeletionShutdown,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.errors.job_errors import JobStoppedError
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_handler import JobHandler


class ProjectDeletionJobHandler(JobHandler):
    """Delegate one original local shutdown without completing its physical-cleanup parent."""

    def __init__(self, project_deletion_shutdown: ProjectDeletionShutdown) -> None:
        self._project_deletion_shutdown = project_deletion_shutdown

    @override
    def payload_type(self) -> tuple[str, int]:
        return "project.application-shutdown", 1

    @override
    async def run(self, context: JobAttemptContextDTO, checkpoints: JobCheckpoints) -> None:
        binding = context.binding
        if not isinstance(binding, ProjectDeletionJobBindingDTO) or (
            context.payload.kind,
            context.payload.version,
            context.payload.data,
        ) != ("project.application-shutdown", 1, binding.obligation_id.bytes):
            raise JobStoppedError("The child does not match original Project shutdown work.")

        await checkpoints.check(context)
        await self._project_deletion_shutdown.shutdown(context)
