from abc import abstractmethod
from collections.abc import AsyncIterable
from contextlib import AbstractAsyncContextManager
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO


class ArtifactPreparationIO(Protocol):
    """Keep local ownership until every native user and borrowed handle has closed.

    Hold owns a separate preparation client, never the worker's shared client.
    A failing/cancelled operation joins that same native drain before unlocking.
    Complete matching readback establishes bytes, not server-side exclusion.
    """

    @abstractmethod
    def hold(self, allocation: ArtifactAllocationDTO) -> AbstractAsyncContextManager[None]: ...

    @abstractmethod
    async def stage(
        self, allocation: ArtifactAllocationDTO, chunks: AsyncIterable[bytes]
    ) -> ArtifactAttemptDTO: ...

    @abstractmethod
    async def verify(self, attempt: ArtifactAttemptDTO, *, upload: bool) -> VerifiedArtifactDTO: ...
