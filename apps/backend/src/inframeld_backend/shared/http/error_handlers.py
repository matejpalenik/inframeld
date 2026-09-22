"""Register the shared HTTP exception-handling boundary."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from inframeld_backend.shared.application.application_error import ApplicationError
from inframeld_backend.shared.http.problem_definitions import (
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    INTERNAL_ERROR_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.problem_mapper import (
    for_application_error,
    for_http_status,
)
from inframeld_backend.shared.http.problem_response import build_problem_response
from inframeld_backend.shared.http.validation import issues_from_request_error
from inframeld_backend.shared.infrastructure.error_reporting import report_unexpected_error


async def _request_validation_handler(
    request: Request,
    error: RequestValidationError,
) -> Response:
    """Return a sanitized RFC 9457 response for invalid request data."""
    return build_problem_response(
        request,
        VALIDATION_ERROR_PROBLEM,
        errors=issues_from_request_error(error),
    )


async def _application_error_handler(
    request: Request,
    error: ApplicationError,
) -> Response:
    """Return the reviewed problem registered for an application failure."""
    definition = for_application_error(error)

    if definition == INTERNAL_ERROR_PROBLEM:
        report_unexpected_error(error, event="request_failed")
    elif definition == DEPENDENCY_UNAVAILABLE_PROBLEM and error.__cause__ is not None:
        report_unexpected_error(error, event="request_failed", error_code=error.code)

    return build_problem_response(request, definition)


async def _http_exception_handler(
    request: Request,
    error: StarletteHTTPException,
) -> Response:
    """Return a safe generic problem while preserving trusted HTTP headers."""
    return build_problem_response(
        request,
        for_http_status(error.status_code),
        protocol_headers=error.headers,
    )


async def _unexpected_error_handler(
    request: Request,
    error: Exception,
) -> Response:
    """Report an unreported failure and return a safe internal problem."""
    response = build_problem_response(
        request,
        INTERNAL_ERROR_PROBLEM,
    )

    raw_request_id = getattr(request.state, "request_id", None)
    request_id = raw_request_id if isinstance(raw_request_id, str) else None

    report_unexpected_error(
        error,
        event="request_failed",
        request_id=request_id,
    )

    return response


def register_error_handlers(application: FastAPI) -> None:
    """Register shared exception handlers on a FastAPI application.

    Args:
        application: Application whose HTTP exception handling is configured.
    """
    application.exception_handler(RequestValidationError)(_request_validation_handler)
    application.exception_handler(ApplicationError)(_application_error_handler)
    application.exception_handler(StarletteHTTPException)(_http_exception_handler)
    application.exception_handler(Exception)(_unexpected_error_handler)
