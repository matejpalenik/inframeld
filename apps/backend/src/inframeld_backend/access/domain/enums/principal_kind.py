from enum import StrEnum


class PrincipalKind(StrEnum):
    """Distinguish local human actors from application accounts."""

    HUMAN = "human"
    APPLICATION = "application"
