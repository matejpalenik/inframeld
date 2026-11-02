from dataclasses import dataclass

from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class ProjectCreationAuthorizationDTO(AuthorizedOperationScope[None]):
    """Carry checked Organization scope and revision for this creation transaction."""

    organization_id: OrganizationId
    access_revision: int
    project_id: None = None
