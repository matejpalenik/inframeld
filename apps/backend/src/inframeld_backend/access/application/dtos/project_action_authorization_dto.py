from dataclasses import dataclass

from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectActionAuthorizationDTO(AuthorizedOperationScope[ProjectId]):
    """Identify the organization and exact project checked for this action attempt."""

    organization_id: OrganizationId
    project_id: ProjectId
