from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
    IdentityRecoveryCleanupClaimDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_run_dto import (
    IdentityRecoveryCleanupRunDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_step_dto import (
    IdentityRecoveryCleanupStepDTO,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupWorkDTO:
    """Observe the original job and active attempt under identity coordination."""

    installation_id: InstallationId
    admission: IdentityRecoveryAdmissionDTO
    evidence_receipt_id: UUID
    has_original_password_receipt: bool
    credential_version: HumanCredentialVersion | None
    kratos_cleanup_state: IdentityRecoveryCleanupState
    released_at: datetime | None
    cli_grants_state: IdentityRecoveryCleanupState
    remembered_logins_state: IdentityRecoveryCleanupState
    cli_confirmation_attempt_id: UUID | None
    login_confirmation_attempt_id: UUID | None
    run: IdentityRecoveryCleanupRunDTO
    claim: IdentityRecoveryCleanupClaimDTO | None
    steps: tuple[IdentityRecoveryCleanupStepDTO, ...]
