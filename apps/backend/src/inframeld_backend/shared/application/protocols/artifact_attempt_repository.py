from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.protocols.artifact_capacity_reader import (
    ArtifactCapacityReader,
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
        capacity_reader: ArtifactCapacityReader,
    ) -> ArtifactStagingReservationDTO:
        """Recover an exact original before measuring capacity for new bytes.

        For fresh allocation, take one local observation under the installation
        ledger turn before creating or changing reservation records.
        """
        ...

    @abstractmethod
    async def inspect(self, allocation: ArtifactAllocationDTO) -> ArtifactStagingReservationDTO: ...

    @abstractmethod
    async def seal(
        self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO
    ) -> None: ...

    @abstractmethod
    async def begin_put(
        self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO
    ) -> bool:
        """Commit a first PUT intent, or require readback of the original intent.

        False never authorizes another dispatch, even when the object is absent.
        """
        ...

    @abstractmethod
    async def confirm_verified(
        self, allocation: ArtifactAllocationDTO, verified: VerifiedArtifactDTO
    ) -> None:
        """Record content integrity while retaining unresolved original PUT evidence."""
        ...

    @abstractmethod
    async def publish_verified(
        self, allocation: ArtifactAllocationDTO, verified: VerifiedArtifactDTO
    ) -> None:
        """Conditionally publish in the owning admission's currently authorized transaction.

        Make the original dormant cleanup job due for local staging removal.
        The owning caller must establish current admission authority.
        """
        ...

    @abstractmethod
    async def prepare_local_removal(
        self, binding: ArtifactCleanupJobBindingDTO, target: ArtifactCleanupTargetDTO
    ) -> bool:
        """Close local growth and report whether the original staging still needs removal."""
        ...

    @abstractmethod
    async def confirm_local_removed(
        self, binding: ArtifactCleanupJobBindingDTO, target: ArtifactCleanupTargetDTO
    ) -> None: ...
