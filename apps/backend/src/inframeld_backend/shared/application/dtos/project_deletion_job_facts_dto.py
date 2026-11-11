from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.deletion_status_binding_dto import (
    DeletionStatusBindingDTO,
)
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload


@dataclass(frozen=True, slots=True)
class ProjectDeletionJobFactsDTO:
    """Observe authentic retained original scope and monotonic local progress.

    Job ID and payload retain original attribution after a completed child retires.
    These facts supply no live job, attempt, fence or physical-effect authority.
    """

    binding: ProjectDeletionJobBindingDTO
    job_id: JobId
    payload: JobPayload
    original: DeletionStatusBindingDTO
    admitted_at: datetime
    observed_at: datetime
    source_revision: int
    shutdown_completed_at: datetime | None = None
    physical_cleanup_completed_at: datetime | None = None
