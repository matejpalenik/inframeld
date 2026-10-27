import math
from dataclasses import dataclass

from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)


@dataclass(frozen=True, slots=True)
class HumanOAuthCleanupOutcomeDTO:
    """Describe one provider observation without claiming recovery is complete."""

    state: IdentityRecoveryCleanupState
    disposition: OAuthCleanupDisposition
    category: OAuthCleanupCategory
    http_status: int | None = None
    retry_after_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.state is IdentityRecoveryCleanupState.PENDING or (
            (self.state is IdentityRecoveryCleanupState.CONFIRMED)
            != (self.disposition is OAuthCleanupDisposition.NOT_NEEDED)
        ):
            raise ValueError("The cleanup observation and retry disposition are incompatible.")

        if self.retry_after_seconds is not None and (
            isinstance(self.retry_after_seconds, bool)
            or not math.isfinite(self.retry_after_seconds)
            or self.retry_after_seconds < 0
        ):
            raise ValueError("The retry delay must be finite and non-negative.")
