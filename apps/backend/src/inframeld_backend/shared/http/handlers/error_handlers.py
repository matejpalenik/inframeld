"""Register the shared HTTP exception-handling boundary."""

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import Response

from inframeld_backend.shared.application.errors.application_error import (
    ApplicationError,
)
from inframeld_backend.shared.application.errors.application_errors import (
    IdempotencyInProgressError,
)
from inframeld_backend.shared.http.builders.problem_response import build_problem_response
from inframeld_backend.shared.http.definitions.problem_catalogue import (
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    IDEMPOTENCY_IN_PROGRESS_PROBLEM,
    INTERNAL_ERROR_PROBLEM,
    INVALID_AUTHENTICATION_REQUEST_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.dependencies.request_identity import request_identity
from inframeld_backend.shared.http.mappers.problem_mapper import (
    for_application_error,
    for_http_status,
)
from inframeld_backend.shared.http.validation.invalid_authentication_request_error import (
    InvalidAuthenticationRequestError,
)
from inframeld_backend.shared.http.validation.request_validation_translator import (
    issues_from_request_error,
)
from inframeld_backend.shared.infrastructure.diagnostics.error_reporting import (
    report_unexpected_error,
)


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

    if (
        isinstance(error, IdempotencyInProgressError)
        and definition == IDEMPOTENCY_IN_PROGRESS_PROBLEM
    ):
        return build_problem_response(
            request,
            definition,
            operation_id=error.operation_id,
            protocol_headers={"Retry-After": str(error.retry_after_seconds)},
        )

    return build_problem_response(request, definition)


async def _http_exception_handler(
    request: Request,
    error: StarletteHTTPException,
) -> Response:
    """Preserve trusted headers and select the specific authentication 400 problem."""
    definition = (
        INVALID_AUTHENTICATION_REQUEST_PROBLEM
        if isinstance(error, InvalidAuthenticationRequestError)
        else for_http_status(error.status_code)
    )
    return build_problem_response(
        request,
        definition,
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

    request_id = request_identity(request)

    report_unexpected_error(
        error,
        event="request_failed",
        request_id=str(request_id.value),
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
