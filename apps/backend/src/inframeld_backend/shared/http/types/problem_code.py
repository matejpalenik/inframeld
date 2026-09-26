from enum import StrEnum


class ProblemCode(StrEnum):
    """Enumerate the problem codes emitted by this server version."""

    VALIDATION_ERROR = "validation_error"
    INVALID_INPUT = "invalid_input"
    RESOURCE_NOT_FOUND = "resource_not_found"
    ACCESS_DENIED = "access_denied"
    CONFLICT = "conflict"
    DEPENDENCY_UNAVAILABLE = "dependency_unavailable"
    INTERNAL_ERROR = "internal_error"
    HTTP_ERROR = "http_error"
