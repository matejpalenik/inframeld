from enum import StrEnum


class HttpMethod(StrEnum):
    """Identify the mutating method bound to an operation and its retry identity."""

    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
