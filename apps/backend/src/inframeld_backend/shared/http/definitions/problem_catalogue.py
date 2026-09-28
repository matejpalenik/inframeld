"""Select reviewed public wording for each supported failure category."""

from inframeld_backend.shared.http.definitions.problem_definition import ProblemDefinition
from inframeld_backend.shared.http.types.problem_code import ProblemCode

TYPE_PREFIX = (
    "https://github.com/matejpalenik/inframeld/blob/main/docs/development/error-handling.md"
)


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

STALE_REVISION_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#stale-revision",
    code=ProblemCode.STALE_REVISION,
    title="Revision is no longer current",
    status=409,
    detail="Reload the current state before making a new change.",
)

IDEMPOTENCY_KEY_REUSED_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#idempotency-key-reused",
    code=ProblemCode.IDEMPOTENCY_KEY_REUSED,
    title="Idempotency key reused",
    status=409,
    detail="This key was already used for a different request.",
)

IDEMPOTENCY_IN_PROGRESS_PROBLEM = ProblemDefinition(
    type_uri=f"{TYPE_PREFIX}#idempotency-in-progress",
    code=ProblemCode.IDEMPOTENCY_IN_PROGRESS,
    title="Operation in progress",
    status=409,
    detail="The original request is still in progress.",
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
