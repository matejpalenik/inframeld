from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.grant_recipients_page_dto import (
    GrantRecipientsPageDTO,
)
from inframeld_backend.access.application.queries.list_project_grant_recipients_query import (
    ListProjectGrantRecipientsQuery,
)


class ProjectGrantRecipientsReader(Protocol):
    @abstractmethod
    async def list_recipients(
        self, *, access: AccessContextDTO, query: ListProjectGrantRecipientsQuery
    ) -> GrantRecipientsPageDTO:
        """Disclose eligible current members of the exact target's authoritative Project.

        Every page requires current eligible-human exact delegation, with only
        the accepted same-group manager alternative. Return principal ID, name
        and kind only, no eligibility reasons, totals or effective permissions.
        """
        ...
