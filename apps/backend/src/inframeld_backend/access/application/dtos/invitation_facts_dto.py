from dataclasses import dataclass

from inframeld_backend.access.application.dtos.invitation_assignment_facts_dto import (
    InvitationAssignmentFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class InvitationFactsDTO(AuthorizedOperationScope[None]):
    """Carry complete current observations after Organization and sorted Project turns."""

    organization_id: OrganizationId
    actor: OrganizationAccessFactsDTO
    assignments: tuple[InvitationAssignmentFactsDTO, ...]
    project_id: None = None
