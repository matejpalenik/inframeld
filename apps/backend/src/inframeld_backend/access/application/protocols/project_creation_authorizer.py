from abc import abstractmethod
from typing import Protocol

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_creation_authorization_dto import (
    ProjectCreationAuthorizationDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


class ProjectCreationAuthorizer(Protocol):
    @abstractmethod
    async def require_creation(
        self, *, access: AccessContextDTO, organization_id: OrganizationId
    ) -> ProjectCreationAuthorizationDTO:
        """Require current eligible human use authority for create-projects.

        Use the caller's coordinated transaction. No starter, existing Project
        membership or delegation level is required. Recheck before every replay.
        """
        ...
