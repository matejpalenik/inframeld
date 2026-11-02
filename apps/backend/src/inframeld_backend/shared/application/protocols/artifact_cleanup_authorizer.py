from abc import abstractmethod
from typing import Protocol

from inframeld_backend.shared.application.dtos.artifact_cleanup_facts_dto import (
    ArtifactCleanupFactsDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId


class ArtifactCleanupAuthorizer(Protocol):
    """Validate exact original cleanup authority before a bounded protected step.

    This grants no product access or blanket object deletion. The handler must
    preserve referenced objects and unknown earlier writes from the returned facts.
    """

    @abstractmethod
    async def require_current(
        self, job_id: JobId, binding: ArtifactCleanupJobBindingDTO
    ) -> ArtifactCleanupFactsDTO: ...
