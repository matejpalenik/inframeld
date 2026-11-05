from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_grants_page_dto import (
    ProjectActionGrantsPageDTO,
)
from inframeld_backend.access.application.queries.list_project_action_grants_query import (
    ListProjectActionGrantsQuery,
)


class ProjectActionGrantsReader(Protocol):
    @abstractmethod
    async def list_grants(
        self,
        *,
        access: AccessContextDTO,
        query: ListProjectActionGrantsQuery,
    ) -> ProjectActionGrantsPageDTO:
        """Read stored assignments under current exact-action use-and-grant authority.

        Recheck eligible-human credentials, Project visibility/membership and
        delegation on every page. Cursors provide position, not authority or a
        traversal snapshot. Do not expand implied/effective permissions or
        filter assignments by recipient eligibility.
        """
        ...
