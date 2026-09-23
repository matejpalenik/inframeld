"""Map handled failures and HTTP statuses to reviewed problem definitions."""

from http import HTTPStatus

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
    ProblemCode,
    ProblemDefinition,
)

_GENERIC_HTTP_ERROR_DETAIL = "The request could not be completed."

_HTTP_ERROR_DETAILS: dict[int, str] = {
    HTTPStatus.UNAUTHORIZED: "Authentication is required.",
    HTTPStatus.NOT_FOUND: "The requested resource was not found.",
    HTTPStatus.METHOD_NOT_ALLOWED: ("The requested method is not allowed for this resource."),
}

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


def for_http_status(status_code: int) -> ProblemDefinition:
    """Create a generic safe problem for an HTTP error status.

    Args:
        status_code: HTTP status emitted by Starlette or an HTTP adapter.

    Returns:
        An ``about:blank`` definition using the standard status phrase and
        reviewed safe detail. Unknown statuses use generic public wording.
    """
    try:
        title = HTTPStatus(status_code).phrase
    except ValueError:
        title = "HTTP error"

    return ProblemDefinition(
        type_uri="about:blank",
        code=ProblemCode.HTTP_ERROR,
        title=title,
        status=status_code,
        detail=_HTTP_ERROR_DETAILS.get(
            status_code,
            _GENERIC_HTTP_ERROR_DETAIL,
        ),
    )
