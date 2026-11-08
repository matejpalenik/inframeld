from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class InvitationActivationBindingDTO:
    """Carry exact pending-operation identity, never cached permission or a native reservation."""

    operation_id: OperationId
    installation_id: InstallationId
    identity: VerifiedHumanIdentityDTO
    organization_id: OrganizationId
    invitation_id: InvitationId
    issuer_principal_id: PrincipalId
    principal_id: PrincipalId | None
    context: IdempotencyContextDTO
    fingerprint: RequestFingerprint
