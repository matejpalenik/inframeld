from enum import StrEnum


class ApplicationEnvironment(StrEnum):
    """Select deployment defaults without changing product authorization."""

    LOCAL = "local"
    TEST = "test"
    PRODUCTION = "production"
