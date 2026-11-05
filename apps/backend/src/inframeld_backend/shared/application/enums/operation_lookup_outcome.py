from enum import StrEnum


class OperationLookupOutcome(StrEnum):
    """Identify what retained evidence establishes about an original operation."""

    COMPLETED_SYNCHRONOUS = "completed_synchronous"
    ACCEPTED_ASYNCHRONOUS = "accepted_asynchronous"
    IN_PROGRESS = "in_progress"
    RECOVERY_REQUIRED = "recovery_required"
    UNRESOLVED = "unresolved"
