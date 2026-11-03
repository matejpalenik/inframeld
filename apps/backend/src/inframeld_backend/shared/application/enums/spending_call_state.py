from enum import StrEnum


class SpendingCallState(StrEnum):
    """Distinguish accounting progress from permission to send a model request."""

    RESERVED = "reserved"
    ACCOUNTING_APPROVED = "accounting_approved"
    UNRESOLVED = "unresolved"
    SETTLED = "settled"
    RELEASED = "released"
