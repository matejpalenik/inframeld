from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupProofDTO:
    """Observe complete source provenance, separately from local release eligibility."""

    installation_id: InstallationId
    admission: IdentityRecoveryAdmissionDTO
    source_admission: IdentityRecoveryAdmissionDTO
    source_receipt_id: UUID
    cli_confirmation_attempt_id: UUID
    login_confirmation_attempt_id: UUID
    has_password_saved_receipt: bool
    source_kratos_cleanup_state: IdentityRecoveryCleanupState
    has_cli_confirmation: bool
    has_login_confirmation: bool
    checked_at: datetime | None
    propagation_complete: bool
