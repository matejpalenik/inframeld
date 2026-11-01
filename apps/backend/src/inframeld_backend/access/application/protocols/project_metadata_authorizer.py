from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


class ProjectMetadataAuthorizer(Protocol):
    """Check current visibility or exact human metadata authority in the caller transaction."""

    @abstractmethod
    async def require_read(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectActionAuthorizationDTO: ...

    @abstractmethod
    async def require_change(
        self, *, access: AccessContextDTO, project_id: ProjectId
    ) -> ProjectActionAuthorizationDTO: ...
