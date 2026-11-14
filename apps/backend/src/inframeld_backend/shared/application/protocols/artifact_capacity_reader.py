from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_capacity_dto import ArtifactCapacityDTO


class ArtifactCapacityReader(Protocol):
    """Observe protected storage capacity locally within an allocation turn."""

    @abstractmethod
    async def read(self) -> ArtifactCapacityDTO:
        """Return a fresh, bounded observation without caching or remote I/O.

        Raise ArtifactCapacityError when local capacity cannot be confirmed.
        """
        ...
