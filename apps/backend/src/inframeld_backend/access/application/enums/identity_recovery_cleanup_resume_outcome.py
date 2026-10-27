from enum import StrEnum


class IdentityRecoveryCleanupResumeOutcome(StrEnum):
    AUTHORIZED = "cleanup-authorized"
    ALREADY_COMPLETED = "already-completed"
    CLEANUP_CONFIRMED = "cleanup-confirmed"
