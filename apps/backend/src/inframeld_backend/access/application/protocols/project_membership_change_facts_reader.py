from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectMembershipChangeFactsReader(Protocol):
    @abstractmethod
    async def read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        principal_id: PrincipalId,
        removing: bool,
    ) -> ProjectMembershipChangeFactsDTO | None:
        """Lock Organization then Project and reread current facts at READ COMMITTED.

        Require the active caller transaction. Provider work is excluded.
        Lock waits share the operation's existing database budget.
        """
        ...
