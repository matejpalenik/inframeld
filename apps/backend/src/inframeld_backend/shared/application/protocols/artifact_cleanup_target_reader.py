from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId


class ArtifactCleanupTargetReader(Protocol):
    """Read one exact obligation target inside the caller's protected short transaction.

    The caller locks the live job before its original obligation and targets.
    This projection grants no cleanup authority and preserves the actual nullable
    length and digest pair. Missing or changed membership returns no target.
    """

    @abstractmethod
    async def read(
        self, binding: ArtifactCleanupJobBindingDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactCleanupTargetDTO | None: ...
