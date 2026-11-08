from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class InvitationRevocationResultDTO:
    """Preserve the original revocation revision without undoing completed assignments."""

    invitation_id: InvitationId
    organization_id: OrganizationId
    access_revision: int
    operation: CompletedSynchronousOperationDTO
