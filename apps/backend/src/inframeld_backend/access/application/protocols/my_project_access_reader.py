from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.my_project_access_page_dto import (
    MyProjectAccessPageDTO,
)
from inframeld_backend.access.application.queries.get_my_project_access_query import (
    GetMyProjectAccessQuery,
)


class MyProjectAccessReader(Protocol):
    @abstractmethod
    async def get_access(
        self, *, access: AccessContextDTO, query: GetMyProjectAccessQuery
    ) -> MyProjectAccessPageDTO:
        """Read a bounded page of this eligible human member's stored Access.

        Require current credentials, eligibility and Project visibility on each
        page. No action grant or membership-management authority is required.
        Return current revision and actual own grants/group relationships only.
        A continuation binds installation, Organization, Project and caller.
        A page is neither a traversal snapshot nor authority for a later write.
        """
        ...
