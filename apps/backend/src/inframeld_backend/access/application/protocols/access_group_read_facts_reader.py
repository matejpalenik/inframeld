from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_principal_dto import (
    AccessGroupPrincipalDTO,
)
from inframeld_backend.access.application.dtos.access_group_read_facts_dto import (
    AccessGroupReadFactsDTO,
)
from inframeld_backend.access.application.enums.access_group_collection import AccessGroupCollection
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName


class AccessGroupReadFactsReader(Protocol):
    @abstractmethod
    async def read(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        selector: AccessGroupId | ResourceName,
    ) -> AccessGroupReadFactsDTO | None:
        """Hold Organization and Project shared coordination through the caller's read."""
        ...

    @abstractmethod
    async def principals(
        self,
        *,
        facts: AccessGroupReadFactsDTO,
        collection: AccessGroupCollection,
        after: PrincipalId | None,
        limit: int,
    ) -> tuple[AccessGroupPrincipalDTO, ...]:
        """Read at most limit plus one safe items after the caller checks current management."""
        ...
