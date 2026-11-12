from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)


@dataclass(frozen=True, slots=True)
class HumanRestorationResultDTO:
    """Return the safe original business outcome without reapplying its transition."""

    organization_id: OrganizationId
    principal_id: PrincipalId
    actor_principal_id: PrincipalId
    access_revision: int
    credential_version: HumanCredentialVersion
    operation: CompletedSynchronousOperationDTO
