from dataclasses import dataclass

from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class OperationLookupAuthorizationDTO(AuthorizedOperationScope[ProjectId | None]):
    """Carry the scope checked for this lookup attempt, not future permission."""

    organization_id: OrganizationId
    project_id: ProjectId | None
