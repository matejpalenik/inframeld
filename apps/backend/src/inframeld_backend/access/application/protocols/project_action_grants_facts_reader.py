from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grants_page_facts_dto import (
    ProjectActionGrantsPageFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectActionGrantsFactsReader(Protocol):
    @abstractmethod
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> ProjectActionGrantsPageFactsDTO | None:
        """Observe current actor/scope and at most limit+1 exact-action assignments.

        Use one SQL snapshot on a clean request-local session. Scope the page
        before position and limit, order by recipient UUID, and retain the
        authority header for empty pages. Preserve suspended recipients' stored
        assignments. Do not authorize, call providers, lock, write or commit.
        Bootstrap owns the session lifetime. Required unavailable dependencies
        fail closed rather than producing an empty successful page.
        """
        ...
