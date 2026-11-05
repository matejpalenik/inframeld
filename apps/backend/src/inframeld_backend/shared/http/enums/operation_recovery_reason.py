from enum import StrEnum


class OperationRecoveryReason(StrEnum):
    """Explain why an original result cannot be returned through ordinary lookup."""

    ORIGINAL_OUTCOME_REQUIRES_RECOVERY = "original_outcome_requires_recovery"
