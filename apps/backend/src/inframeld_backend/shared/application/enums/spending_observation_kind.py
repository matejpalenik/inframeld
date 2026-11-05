from enum import StrEnum


class SpendingObservationKind(StrEnum):
    """Distinguish accounting evidence from an unresolved or unbilled model call."""

    USAGE = "usage"
    CHARGE = "charge"
    NOT_SENT = "not_sent"
    NOT_BILLED = "not_billed"
    UNCERTAIN = "uncertain"
