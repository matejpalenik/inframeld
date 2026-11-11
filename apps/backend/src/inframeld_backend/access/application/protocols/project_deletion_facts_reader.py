from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_deletion_facts_dto import (
    ProjectDeletionFactsDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectDeletionFactsReader(Protocol):
    @abstractmethod
    async def lock_for_deletion(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectDeletionFactsDTO | None:
        """Observe current exact Delete-project facts in the caller's READ COMMITTED transaction.

        Take Organization-shared then Project-exclusive coordination and refresh
        credential, actor, membership, action and revision facts after waits.
        Include a blocked Project for ordinary original recovery, never invent
        active status or saved authority. Missing scope returns None.
        Commit, rollback and the original five-second deadline stay with caller.
        """
        ...
