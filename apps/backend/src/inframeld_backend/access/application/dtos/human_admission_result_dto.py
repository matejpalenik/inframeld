from dataclasses import dataclass

from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class HumanAdmissionResultDTO:
    """Retain original admission meaning separately from generic replay metadata."""

    installation_id: InstallationId
    identity: VerifiedHumanIdentityDTO
    organization_id: OrganizationId
    actor_principal_id: PrincipalId
    principal_id: PrincipalId
    access_revision: int
    changed: bool
    operation: CompletedSynchronousOperationDTO
