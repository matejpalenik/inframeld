from enum import StrEnum


class ModelPropertyState(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    CONFLICT = "conflict"
