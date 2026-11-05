from enum import StrEnum


class JobEffectAction(StrEnum):
    """Identify the original storage mutation without asserting its outcome."""

    PUT = "put"
    DELETE = "delete"
