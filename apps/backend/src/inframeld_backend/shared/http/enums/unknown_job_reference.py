from enum import StrEnum


class UnknownJobReference(StrEnum):
    """Keep the absence of a known job correlation closed on every generated client."""

    UNKNOWN = "unknown"
