from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId


@dataclass(frozen=True, slots=True)
class ArtifactAllocationDTO:
    """Return only a committed byte reservation with its original cleanup slot."""

    reservation: ArtifactStagingReservationDTO
    cleanup_binding: ArtifactCleanupJobBindingDTO
    cleanup_job_id: JobId
