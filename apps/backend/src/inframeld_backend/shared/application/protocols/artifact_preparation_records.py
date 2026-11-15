from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO


class ArtifactPreparationRecords(Protocol):
    """Commit one exact transition in a fresh bounded session, closed before returning.

    These private preparation operations own their short transactions. Publication
    remains on ArtifactAttemptRepository in the owning admission's transaction.
    """

    @abstractmethod
    async def inspect(self, allocation: ArtifactAllocationDTO) -> ArtifactStagingReservationDTO: ...

    @abstractmethod
    async def seal(
        self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO
    ) -> None: ...

    @abstractmethod
    async def begin_put(
        self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO
    ) -> bool: ...

    @abstractmethod
    async def confirm_verified(
        self, allocation: ArtifactAllocationDTO, verified: VerifiedArtifactDTO
    ) -> None: ...
