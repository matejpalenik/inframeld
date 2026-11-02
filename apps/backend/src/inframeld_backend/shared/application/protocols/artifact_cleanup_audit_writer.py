from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_cleanup_admission_dto import (
    ArtifactCleanupAdmissionDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)


class ArtifactCleanupAuditWriter(Protocol):
    @abstractmethod
    async def append(
        self, admission: ArtifactCleanupAdmissionDTO, binding: ArtifactCleanupJobBindingDTO
    ) -> None: ...
