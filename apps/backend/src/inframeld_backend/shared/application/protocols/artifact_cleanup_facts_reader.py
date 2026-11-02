from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_cleanup_facts_dto import (
    ArtifactCleanupFactsDTO,
)
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)


class ArtifactCleanupFactsReader(Protocol):
    """Read persisted obligation meaning and owned targets, never caller-selected proof."""

    @abstractmethod
    async def read(
        self, obligation_id: ArtifactCleanupObligationId
    ) -> ArtifactCleanupFactsDTO | None: ...
