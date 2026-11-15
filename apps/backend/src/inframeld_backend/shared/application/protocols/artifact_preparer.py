from abc import abstractmethod
from collections.abc import AsyncIterable
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO


class ArtifactPreparer(Protocol):
    @abstractmethod
    async def prepare(
        self, allocation: ArtifactAllocationDTO, chunks: AsyncIterable[bytes]
    ) -> VerifiedArtifactDTO: ...

    @abstractmethod
    async def resume(self, allocation: ArtifactAllocationDTO) -> VerifiedArtifactDTO: ...
