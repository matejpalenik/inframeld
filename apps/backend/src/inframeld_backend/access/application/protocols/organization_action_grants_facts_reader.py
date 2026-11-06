from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.organization_action_grants_page_facts_dto import (
    OrganizationActionGrantsPageFactsDTO,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId


class OrganizationActionGrantsFactsReader(Protocol):
    @abstractmethod
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> OrganizationActionGrantsPageFactsDTO | None:
        """Observe current authority and at most limit+1 stored rows in one SQL snapshot.

        Filter scope and action before UUID position and limit. Retain authority
        facts for empty pages. Do not authorize, lock, write or hide suspended
        recipients. Bootstrap owns the clean request-local session lifetime.
        """
        ...
