from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.invitation_scope_dto import InvitationScopeDTO
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId


@dataclass(frozen=True, slots=True)
class InvitationPreviewResultDTO:
    invitation_id: InvitationId
    organization_id: OrganizationId
    assignments: tuple[InvitationAssignmentDTO, ...]
    expires_at: datetime
    scopes: tuple[InvitationScopeDTO, ...]
