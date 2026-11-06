from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_read_facts_dto import (
    AccessGroupReadFactsDTO,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class AccessGroupDeletionFactsReader(Protocol):
    @abstractmethod
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, project_id: ProjectId, group_id: AccessGroupId
    ) -> AccessGroupReadFactsDTO | None:
        """Observe exact current management under Organization-shared then Project-exclusive coordination."""
        ...
