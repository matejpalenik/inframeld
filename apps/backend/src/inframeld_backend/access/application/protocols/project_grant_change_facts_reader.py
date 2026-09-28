from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectGrantChangeFactsReader(Protocol):
    """Lock the Access scope and read facts in the caller's transaction."""

    @abstractmethod
    async def read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantChangeFactsDTO | None:
        """Return None if the actor or project is unavailable in the actor's organization.

        The recipient may be absent - the application service decides how to
        report that after checking the actor's authority. Do not commit.
        """
        ...
