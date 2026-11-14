from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class ProcessingProfileReadRepository(Protocol):
    """Observe current scope and exact View assignments within one transaction."""

    @abstractmethod
    async def lock_scope(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> tuple[InstallationId, ProjectActionFactsDTO] | None: ...

    @abstractmethod
    async def get_visible(
        self, facts: ProjectActionFactsDTO, project_id: ProjectId, profile_id: ProcessingProfileId
    ) -> ProcessingProfileDTO | None: ...

    @abstractmethod
    async def list_visible(
        self,
        facts: ProjectActionFactsDTO,
        project_id: ProjectId,
        after: ProcessingProfileId | None,
        limit: int,
    ) -> tuple[ProcessingProfileDTO, ...]:
        """Apply exact View before taking the requested number of ascending UUIDs."""
        ...
