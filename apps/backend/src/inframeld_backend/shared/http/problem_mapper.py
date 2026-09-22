"""Map supported application errors to reviewed HTTP problem definitions."""

from inframeld_backend.shared.application.application_error import ApplicationError
from inframeld_backend.shared.application.errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.http.problem_definitions import (
    ACCESS_DENIED_PROBLEM,
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INTERNAL_ERROR_PROBLEM,
    INVALID_INPUT_PROBLEM,
    RESOURCE_NOT_FOUND_PROBLEM,
    ProblemDefinition,
)

_APPLICATION_PROBLEMS: dict[type[ApplicationError], ProblemDefinition] = {
    InvalidInputError: INVALID_INPUT_PROBLEM,
    ResourceNotFoundError: RESOURCE_NOT_FOUND_PROBLEM,
    AccessDeniedError: ACCESS_DENIED_PROBLEM,
    ConflictError: CONFLICT_PROBLEM,
    DependencyUnavailableError: DEPENDENCY_UNAVAILABLE_PROBLEM,
}


def for_application_error(error: ApplicationError) -> ProblemDefinition:
    """Return the reviewed HTTP problem for an application error.

    Args:
        error: Transport-neutral application error classified by exact type.

    Returns:
        The registered definition, or the safe internal-error definition when
        the concrete error type has not been registered.
    """
    return _APPLICATION_PROBLEMS.get(type(error), INTERNAL_ERROR_PROBLEM)
