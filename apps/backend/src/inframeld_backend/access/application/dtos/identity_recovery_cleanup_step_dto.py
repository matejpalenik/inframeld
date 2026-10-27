from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_step import (
    IdentityRecoveryCleanupStep,
)


@dataclass(frozen=True, slots=True)
class IdentityRecoveryCleanupStepDTO:
    step: IdentityRecoveryCleanupStep
    dispatched_at: datetime
    outcome: HumanOAuthCleanupOutcomeDTO | None
