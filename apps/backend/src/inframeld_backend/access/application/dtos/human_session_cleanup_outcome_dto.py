from dataclasses import dataclass

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)


@dataclass(frozen=True, slots=True)
class HumanSessionCleanupOutcomeDTO:
    """Retain a safe provider observation, never proof of non-dispatch or retry permission."""

    state: IdentityRecoveryCleanupState
    http_status: int | None = None

    def __post_init__(self) -> None:
        if self.state is IdentityRecoveryCleanupState.PENDING:
            raise ValueError("Pending is not a provider cleanup observation.")
        if self.http_status is not None and (
            type(self.http_status) is not int or not 100 <= self.http_status <= 599
        ):
            raise ValueError("A provider HTTP status must be an integer in range.")
        if self.state is IdentityRecoveryCleanupState.CONFIRMED and self.http_status != 204:
            raise ValueError("Confirmed session cleanup requires its successful acknowledgment.")
        if self.state is IdentityRecoveryCleanupState.FAILED and (
            self.http_status is None
            or not 400 <= self.http_status <= 499
            or self.http_status == 408
        ):
            raise ValueError("A failed session observation requires explicit provider rejection.")
