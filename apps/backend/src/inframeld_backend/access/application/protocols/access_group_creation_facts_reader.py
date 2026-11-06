from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_creation_facts_dto import (
    AccessGroupCreationFactsDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class AccessGroupCreationFactsReader(Protocol):
    @abstractmethod
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> AccessGroupCreationFactsDTO | None:
        """Read fresh exact creation facts under Organization then Project locks.

        Use the caller's READ COMMITTED transaction and retain its coordination
        turn through commit. Never reserve work or interpret authorization.
        """
        ...
