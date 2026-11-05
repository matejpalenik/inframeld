from enum import StrEnum


class DeletionStatusOutcome(StrEnum):
    """Distinguish retained deletion evidence from an unresolved lookup."""

    RETAINED = "retained"
    UNRESOLVED = "unresolved"
