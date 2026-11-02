from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_cleanup_admission_dto import (
    ArtifactCleanupAdmissionDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)


class ArtifactCleanupAdmissionWriter(Protocol):
    """Reserve the same finite queue for one persisted exact obligation.

    Validate original ownership inside the caller transaction. No product
    idempotency reservation, fabricated principal or replacement budget exists.
    """

    @abstractmethod
    async def admit(
        self, binding: ArtifactCleanupJobBindingDTO, *, capacity: int = 8
    ) -> ArtifactCleanupAdmissionDTO: ...
