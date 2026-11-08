from dataclasses import dataclass

from inframeld_backend.access.application.dtos.invitation_project_access_revision_dto import (
    InvitationProjectAccessRevisionDTO,
)
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class InvitationActivationResultDTO:
    """Retain final original scope revisions independently of later permission changes."""

    invitation_id: InvitationId
    organization_id: OrganizationId
    principal_id: PrincipalId
    organization_access_revision: int
    project_access_revisions: tuple[InvitationProjectAccessRevisionDTO, ...]
    operation: CompletedSynchronousOperationDTO
