from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_members_page_dto import ProjectMembersPageDTO
from inframeld_backend.access.application.queries.list_project_members_query import (
    ListProjectMembersQuery,
)


class ProjectMembersReader(Protocol):
    @abstractmethod
    async def list_members(
        self, *, access: AccessContextDTO, query: ListProjectMembersQuery
    ) -> ProjectMembersPageDTO:
        """Return one safe page under current human membership-management use authority.

        Recheck eligibility, visibility and exact authority for every page.
        Cursors grant no permission and promise neither expiry nor a snapshot.
        Preserve stored member labels and kinds, including suspended members.
        """
        ...
