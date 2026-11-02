from dataclasses import dataclass

from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId


@dataclass(frozen=True, slots=True)
class ArtifactCleanupAdmissionDTO:
    job_id: JobId
    obligation_id: ArtifactCleanupObligationId
    created: bool
