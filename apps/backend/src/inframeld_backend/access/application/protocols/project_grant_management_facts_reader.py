from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectGrantManagementFactsReader(Protocol):
    @abstractmethod
    async def read_for_management(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectActionGrantManagementFactsDTO | None:
        """Coordinate Org then Project and observe current actor/recipient facts.

        Require the active caller transaction and READ COMMITTED before any
        decision observation. Preserve the existing bounded database deadline.
        Return exact-action other-grantor observations, excluding the recipient.
        Do not authorize, commit, reserve or silently filter recipient inactivity.
        The owning service decides fresh PUT, DELETE and replay differently.
        """
        ...
