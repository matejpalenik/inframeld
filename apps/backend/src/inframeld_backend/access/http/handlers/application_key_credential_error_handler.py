from http import HTTPStatus

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

from inframeld_backend.access.application.errors.application_key_credential_rejected_error import (
    ApplicationKeyCredentialRejectedError,
)
from inframeld_backend.shared.http.builders.problem_response import build_problem_response
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status


async def _rejected_credential(
    request: Request, error: ApplicationKeyCredentialRejectedError
) -> Response:
    return build_problem_response(
        request,
        for_http_status(HTTPStatus.UNAUTHORIZED),
        protocol_headers={
            "WWW-Authenticate": 'Bearer realm="inframeld", error="invalid_token"',
        },
    )


def register_application_key_credential_error_handler(application: FastAPI) -> None:
    """Retain the Bearer challenge when current authorization rejects a key."""
    application.exception_handler(ApplicationKeyCredentialRejectedError)(_rejected_credential)
