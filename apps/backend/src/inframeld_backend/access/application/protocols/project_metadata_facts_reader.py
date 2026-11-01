from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_metadata_authorization_facts_dto import (
    ProjectMetadataAuthorizationFactsDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.resource_name_scope_dto import ResourceNameScopeDTO


class ProjectMetadataFactsReader(Protocol):
    """Return current scoped observations. Change reads retain Access locks until commit."""

    @abstractmethod
    async def read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectMetadataAuthorizationFactsDTO | None: ...

    @abstractmethod
    async def read_for_change(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectMetadataAuthorizationFactsDTO | None: ...

    @abstractmethod
    async def scope(self, *, access: AccessContextDTO) -> ResourceNameScopeDTO: ...
