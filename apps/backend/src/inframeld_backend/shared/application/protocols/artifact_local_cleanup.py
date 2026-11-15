from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO


class ArtifactLocalCleanup(Protocol):
    """Retire the exact local target, then acknowledge only durable local removal.

    Preparation closes SQL before filesystem ownership is acquired. None means
    authoritative saved local removal, independently of any remote DELETE ACK.
    Confirmation follows joined holders and durable exact absence. Neither call
    releases remote charges or establishes server-side exclusion.
    """

    @abstractmethod
    async def prepare_local(
        self, context: JobAttemptContextDTO
    ) -> ArtifactCleanupTargetDTO | None: ...

    @abstractmethod
    async def confirm_local(
        self, context: JobAttemptContextDTO, target: ArtifactCleanupTargetDTO
    ) -> None: ...
