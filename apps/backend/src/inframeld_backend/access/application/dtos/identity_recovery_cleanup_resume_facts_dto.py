from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupResumeFactsDTO:
    released_at: datetime | None
    kratos_cleanup_state: IdentityRecoveryCleanupState
    hydra_cleanup_state: IdentityRecoveryCleanupState
    has_complete_proof: bool
    work: IdentityRecoveryCleanupWorkDTO | None
