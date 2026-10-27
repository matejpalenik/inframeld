from dataclasses import dataclass

from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId


@dataclass(frozen=True, slots=True)
class ProjectGrantAuthorizationDTO(AuthorizedOperationScope[ProjectId]):
    """Current scope and revision established by grant authorization.

    Use this result within the same transaction that holds the Access locks.
    It does not establish permission for a later request.
    """

    organization_id: OrganizationId
    project_id: ProjectId
    project_access_revision: int
