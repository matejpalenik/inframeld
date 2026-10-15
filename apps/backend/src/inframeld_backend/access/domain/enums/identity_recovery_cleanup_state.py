from enum import StrEnum


class IdentityRecoveryCleanupState(StrEnum):
    """Distinguish unfinished cleanup from confirmed provider evidence."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
