from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_members_page_facts_dto import (
    ProjectMembersPageFactsDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectMembersFactsReader(Protocol):
    @abstractmethod
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        after: PrincipalId | None,
        limit: int,
    ) -> ProjectMembersPageFactsDTO | None:
        """Observe at most limit+1 scoped relationships with a coherent authority header.

        Use one bounded SQL statement on the clean request-local session. Apply
        current actor/Organization/Project binding before position and limit.
        Order by principal UUID and retain the header when no member follows.
        Do not filter target members by eligibility, commit, call providers or
        treat a cursor position as scope. Bootstrap owns the session lifetime.
        """
        ...
