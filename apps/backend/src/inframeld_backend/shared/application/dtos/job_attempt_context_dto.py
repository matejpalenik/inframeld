from dataclasses import dataclass, field
from datetime import datetime

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.project_deletion_job_binding_dto import (
    ProjectDeletionJobBindingDTO,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload


@dataclass(frozen=True, slots=True)
class JobAttemptContextDTO:
    """Carry original work and the current fence, never cached permission or a session."""

    job_id: JobId
    binding: ProductJobBindingDTO | ArtifactCleanupJobBindingDTO | ProjectDeletionJobBindingDTO
    payload: JobPayload
    attempt: int
    fence: JobFence
    work_deadline: datetime
    checkpoint: bytes = field(repr=False)
