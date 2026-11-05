from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)


class ArtifactStagingReservationReader(Protocol):
    """Read current exact reservation facts before any new private bytes are created.

    The owning allocator must atomically reserve capacity, obligation and cleanup
    queue slot first. This reader neither allocates nor releases that capacity.
    """

    @abstractmethod
    async def read(
        self, reservation_id: ArtifactStagingReservationId
    ) -> ArtifactStagingReservationDTO | None: ...

    @abstractmethod
    async def read_attempt(
        self, attempt_id: ArtifactAttemptId
    ) -> ArtifactStagingReservationDTO | None: ...
