from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.application.dtos.processing_profile_dto import ProcessingProfileDTO
from inframeld_backend.indexing.application.dtos.processing_profiles_page_dto import (
    ProcessingProfilesPageDTO,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)


class ProcessingProfileReader(Protocol):
    """Read exact definitions visible to the current Project actor."""

    @abstractmethod
    async def get(
        self, access: AccessContextDTO, project_id: ProjectId, profile_id: ProcessingProfileId
    ) -> ProcessingProfileDTO: ...

    @abstractmethod
    async def list_profiles(
        self, access: AccessContextDTO, project_id: ProjectId, limit: int, cursor: str | None
    ) -> ProcessingProfilesPageDTO: ...
