from dataclasses import dataclass, field
from datetime import datetime

from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token import InvitationToken
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class InvitationIssueResultDTO:
    """Return original safe metadata and the secret only on first authorized delivery."""

    invitation_id: InvitationId
    organization_id: OrganizationId
    assignments: tuple[InvitationAssignmentDTO, ...]
    expires_at: datetime
    access_revision: int
    operation: CompletedSynchronousOperationDTO
    token: InvitationToken | None = field(repr=False)
