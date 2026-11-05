from enum import StrEnum


class LogLevel(StrEnum):
    """Select diagnostic severity without changing safe log contents."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
