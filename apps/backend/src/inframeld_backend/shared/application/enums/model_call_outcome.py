from enum import StrEnum


class ModelCallOutcome(StrEnum):
    ACCEPTED = "accepted"
    FAILED = "failed"
    UNCERTAIN = "uncertain"
