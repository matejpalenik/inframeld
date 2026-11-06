from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_metadata_dto import (
    AccessGroupMetadataDTO,
)
from inframeld_backend.access.application.dtos.access_group_principals_page_dto import (
    AccessGroupPrincipalsPageDTO,
)
from inframeld_backend.access.application.queries.list_access_group_principals_query import (
    ListAccessGroupPrincipalsQuery,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class AccessGroupReader(Protocol):
    @abstractmethod
    async def inspect(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
    ) -> AccessGroupMetadataDTO:
        """Read safe exact metadata under membership, management or exact group-action visibility."""
        ...

    @abstractmethod
    async def list_principals(
        self, *, access: AccessContextDTO, query: ListAccessGroupPrincipalsQuery
    ) -> AccessGroupPrincipalsPageDTO:
        """Require current human management on each bounded UUID-ordered page."""
        ...
