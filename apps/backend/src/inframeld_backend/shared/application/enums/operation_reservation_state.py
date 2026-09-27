from enum import StrEnum


class OperationReservationState(StrEnum):
    """Describe whether a repeated request has a safe recorded outcome."""

    IN_PROGRESS = "in_progress"
    REPLAYABLE = "replayable"
    RECOVERY_REQUIRED = "recovery_required"
