from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId


@dataclass(frozen=True, slots=True)
class InvitationRecordDTO:
    """Retain immutable intent independently of the shorter issuance retry history.

    The digest is verification material, never a replayable token. Current authority
    and fresh validity still need observations under the owning coordinated turn.
    """

    invitation_id: InvitationId
    organization_id: OrganizationId
    issuer_principal_id: PrincipalId
    digest: InvitationTokenDigest
    assignments: tuple[InvitationAssignmentDTO, ...]
    issued_operation_id: OperationId
    issued_access_revision: int
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None
    consumed_at: datetime | None = None
    consumed_by_principal_id: PrincipalId | None = None
