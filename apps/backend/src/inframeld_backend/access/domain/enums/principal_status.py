from enum import StrEnum


class PrincipalStatus(StrEnum):
    """Describe whether a local actor is active, suspended, or permanently retired."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    RETIRED = "retired"
