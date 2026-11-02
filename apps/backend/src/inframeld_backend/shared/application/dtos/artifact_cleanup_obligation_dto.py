from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.domain.enums.job_status import JobStatus


@dataclass(frozen=True, slots=True)
class ArtifactCleanupObligationDTO:
    """Keep physical progress independently of the execution's terminal outcome."""

    binding: ArtifactCleanupJobBindingDTO
    targets: tuple[ArtifactAttemptId, ...]
    transfer_deadline: datetime
    observed_at: datetime
    job_id: JobId | None
    physically_complete: bool
    execution_status: JobStatus | None
