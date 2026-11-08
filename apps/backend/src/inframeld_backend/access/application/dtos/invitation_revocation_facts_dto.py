from dataclasses import dataclass

from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class InvitationRevocationFactsDTO(AuthorizedOperationScope[None]):
    """Observe current administration and retained intent under the Organization turn."""

    organization_id: OrganizationId
    actor: OrganizationAccessFactsDTO
    invitation: InvitationRecordDTO
    project_id: None = None
