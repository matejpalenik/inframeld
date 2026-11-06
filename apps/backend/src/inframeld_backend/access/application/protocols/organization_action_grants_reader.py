from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.organization_action_grants_page_dto import (
    OrganizationActionGrantsPageDTO,
)
from inframeld_backend.access.application.queries.list_organization_action_grants_query import (
    ListOrganizationActionGrantsQuery,
)


class OrganizationActionGrantsReader(Protocol):
    @abstractmethod
    async def list_grants(
        self, *, access: AccessContextDTO, query: ListOrganizationActionGrantsQuery
    ) -> OrganizationActionGrantsPageDTO:
        """Read one exact action's stored assignments under current human authority.

        Suspended recipients remain stored assignments. Every page checks current
        exact delegation, or the current same-group management alternative where
        applicable. Return no totals, revision, secrets or effective-permission expansion.
        """
        ...
