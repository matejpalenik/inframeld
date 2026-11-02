from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.job_id import JobId


@dataclass(frozen=True, slots=True)
class ArtifactCleanupFactsDTO:
    """Observe original ownership and current retirement gates inside the caller transaction."""

    binding: ArtifactCleanupJobBindingDTO
    job_id: JobId
    targets: tuple[ArtifactAttemptId, ...]
    owns_targets: bool
    retirement_authorized: bool
    retention_allows_cleanup: bool
    published: bool
    pending_write: bool

    physically_complete: bool = False
