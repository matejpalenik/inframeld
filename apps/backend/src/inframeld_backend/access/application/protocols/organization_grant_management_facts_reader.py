from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class OrganizationGrantManagementFactsReader(Protocol):
    @abstractmethod
    async def lock_for_management(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> OrganizationGrantManagementFactsDTO | None:
        """Lock the Organization exclusively before rereading this attempt's facts.

        Use the active caller transaction and retained five-second bound. Return
        only the actor's Organization. Observe other exact-action grantors after
        coordination, without deciding their eligibility or authorizing history.
        """
        ...
