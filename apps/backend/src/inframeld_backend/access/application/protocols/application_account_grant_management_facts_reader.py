from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ApplicationAccountGrantManagementFactsReader(Protocol):
    @abstractmethod
    async def lock_for_management(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ApplicationAccountGrantManagementFactsDTO | None:
        """Take shared Organization then exclusive Project locks and reread current facts.

        Use the caller's active READ COMMITTED transaction and bounded waits.
        Observe exact live target scope, actor, recipient and remaining human
        responsibilities without searching history or deciding authorization.
        """
        ...
