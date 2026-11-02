from abc import abstractmethod
from datetime import datetime
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_obligation_dto import (
    ArtifactCleanupObligationDTO,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)


class ArtifactCleanupObligationRepository(Protocol):
    @abstractmethod
    async def create_staging(
        self,
        binding: ArtifactCleanupJobBindingDTO,
        *,
        targets: tuple[ArtifactAttemptId, ...],
        transfer_deadline: datetime,
    ) -> ArtifactCleanupObligationDTO:
        """Bind one original staging reservation without replacing its cleanup meaning.

        Replays preserve obligation ID, origin, request, target and fixed deadline.
        Later retirement obligations are distinct from this staging allocation.
        """
        ...

    @abstractmethod
    async def get(
        self, obligation_id: ArtifactCleanupObligationId
    ) -> ArtifactCleanupObligationDTO | None: ...
