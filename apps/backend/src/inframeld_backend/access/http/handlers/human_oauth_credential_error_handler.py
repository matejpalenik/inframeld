from http import HTTPStatus

from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.shared.http.builders.problem_response import build_problem_response
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status


async def _rejected_credential(
    request: Request, error: HumanOAuthCredentialRejectedError
) -> Response:
    return build_problem_response(
        request,
        for_http_status(HTTPStatus.UNAUTHORIZED),
        protocol_headers={
            "WWW-Authenticate": 'Bearer realm="inframeld", error="invalid_token"',
        },
    )


def register_human_oauth_credential_error_handler(application: FastAPI) -> None:
    """Preserve the Bearer challenge when a transaction detects a stale CLI binding."""
    application.exception_handler(HumanOAuthCredentialRejectedError)(_rejected_credential)
