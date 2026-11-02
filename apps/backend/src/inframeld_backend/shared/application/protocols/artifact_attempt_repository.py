from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_capacity_dto import ArtifactCapacityDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)


class ArtifactAttemptRepository(Protocol):
    """Persist server-owned attempts and finite bytes in the caller transaction.

    Reservation alone is not permission to write. The owning allocation service
    also persists the original obligation and cleanup job before committing.
    """

    @abstractmethod
    async def reserve(
        self,
        *,
        scope: ArtifactScopeDTO,
        artifact_id: ArtifactId,
        attempt_id: ArtifactAttemptId,
        reservation_id: ArtifactStagingReservationId,
        limit_bytes: int,
        transfer_seconds: float,
        capacity: ArtifactCapacityDTO,
    ) -> ArtifactStagingReservationDTO: ...
