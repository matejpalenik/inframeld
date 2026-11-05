from enum import StrEnum


class LogFormat(StrEnum):
    """Select human or machine diagnostic rendering."""

    CONSOLE = "console"
    JSON = "json"
