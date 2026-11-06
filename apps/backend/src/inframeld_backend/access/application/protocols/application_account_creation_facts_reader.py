from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_creation_facts_dto import (
    ApplicationAccountCreationFactsDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ApplicationAccountCreationFactsReader(Protocol):
    @abstractmethod
    async def lock_for_creation(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ApplicationAccountCreationFactsDTO | None:
        """Read fresh exact creation facts under Organization then Project locks.

        Use the caller's READ COMMITTED transaction and retain its coordination
        turn through commit. Never reserve work or interpret authorization.
        """
        ...
