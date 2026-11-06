from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_action_grants_page_dto import (
    AccessGroupActionGrantsPageDTO,
)
from inframeld_backend.access.application.queries.list_access_group_action_grants_query import (
    ListAccessGroupActionGrantsQuery,
)


class AccessGroupActionGrantsReader(Protocol):
    @abstractmethod
    async def list_grants(
        self, *, access: AccessContextDTO, query: ListAccessGroupActionGrantsQuery
    ) -> AccessGroupActionGrantsPageDTO:
        """Read one exact action's stored assignments under current human authority.

        Suspended recipients remain stored assignments. Every page checks current
        exact delegation, or the current same-group management alternative where
        applicable. Return no totals, revision, secrets or effective-permission expansion.
        """
        ...
