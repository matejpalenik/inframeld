from dataclasses import dataclass

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCompletionFactsDTO:
    """Observe the original admission and current local account in one transaction.

    A missing principal means no local identity link exists. Other pending
    recoveries remain independent blocks, even when this checklist can finish.
    """

    installation_id: InstallationId
    admission: IdentityRecoveryAdmissionDTO
    principal: Principal | None
    has_other_pending_recovery: bool
