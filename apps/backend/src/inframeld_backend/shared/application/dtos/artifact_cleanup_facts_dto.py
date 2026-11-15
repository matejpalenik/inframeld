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
    published_staging_removed: bool = False

    def execution_complete(self, *, checkpoint: bytes, pending_effect: str | None) -> bool:
        """Accept published local removal only for a job with no remote effect history."""
        if self.published:
            return self.published_staging_removed and checkpoint == b"" and pending_effect is None
        return self.physically_complete
