from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.processing_profile_grants_page_dto import (
    ProcessingProfileGrantsPageDTO,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)


class ProcessingProfileGrantsReader(Protocol):
    @abstractmethod
    async def list_grants(
        self,
        access: AccessContextDTO,
        profile_id: ProcessingProfileId,
        action: ProcessingProfileAction,
        limit: int,
        cursor: str | None,
    ) -> ProcessingProfileGrantsPageDTO: ...
