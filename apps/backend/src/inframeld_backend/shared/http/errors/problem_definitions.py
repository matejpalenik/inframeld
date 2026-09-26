"""Define the stable RFC 9457 problem catalogue emitted by the HTTP adapter."""

from dataclasses import dataclass
from enum import StrEnum

TYPE_PREFIX = (
    "https://github.com/matejpalenik/inframeld/blob/main/docs/development/error-handling.md"
)


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


@dataclass(frozen=True, slots=True)
class ProblemDefinition:
    """Define one stable public problem representation."""

    type_uri: str
    code: ProblemCode
    title: str
    status: int
    detail: str


VALIDATION_ERROR_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#validation-error",
    code=ProblemCode.VALIDATION_ERROR,
    title="Request validation failed",
    status=422,
    detail="One or more request fields are invalid.",
)


INVALID_INPUT_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#invalid-input",
    code=ProblemCode.INVALID_INPUT,
    title="Invalid input",
    status=422,
    detail="The supplied input is not valid for this operation.",
)

RESOURCE_NOT_FOUND_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#resource-not-found",
    code=ProblemCode.RESOURCE_NOT_FOUND,
    title="Resource not found",
    status=404,
    detail="The requested resource is not available.",
)

ACCESS_DENIED_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#access-denied",
    code=ProblemCode.ACCESS_DENIED,
    title="Access denied",
    status=403,
    detail="You are not allowed to perform this operation.",
)

CONFLICT_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#conflict",
    code=ProblemCode.CONFLICT,
    title="Operation conflicts with current state",
    status=409,
    detail="The operation cannot be completed in the current state.",
)

DEPENDENCY_UNAVAILABLE_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#dependency-unavailable",
    code=ProblemCode.DEPENDENCY_UNAVAILABLE,
    title="Dependency unavailable",
    status=503,
    detail="A required service is unavailable.",
)

INTERNAL_ERROR_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#internal-error",
    code=ProblemCode.INTERNAL_ERROR,
    title="Internal server error",
    status=500,
    detail="An unexpected error occurred.",
)
