from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_capacity_dto import ArtifactCapacityDTO


class ArtifactCapacityReader(Protocol):
    @abstractmethod
    async def read(self) -> ArtifactCapacityDTO: ...
