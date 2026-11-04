from dataclasses import dataclass

from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class HumanAdmissionAuthorizationDTO(AuthorizedOperationScope[None]):
    organization_id: OrganizationId
    access_revision: int
    project_id: None = None
