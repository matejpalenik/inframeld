from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)


@dataclass(frozen=True, slots=True)
class ArtifactStagingReservationDTO:
    """Observe exact capacity ownership and a fixed deadline at the authoritative clock."""

    reservation_id: ArtifactStagingReservationId
    artifact_id: ArtifactId
    attempt_id: ArtifactAttemptId
    scope: ArtifactScopeDTO
    limit_bytes: int
    expires_at: datetime
    observed_at: datetime
    released: bool = False
