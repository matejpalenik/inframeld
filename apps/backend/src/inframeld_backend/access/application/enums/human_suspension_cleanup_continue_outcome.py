from enum import StrEnum


class HumanSuspensionCleanupContinueOutcome(StrEnum):
    REQUEUED = "requeued"
    ALREADY_SCHEDULED = "already-scheduled"
    ALREADY_COMPLETE = "already-complete"
