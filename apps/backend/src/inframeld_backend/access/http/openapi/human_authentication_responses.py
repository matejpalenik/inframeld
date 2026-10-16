"""Describe authentication problems and optional trusted Bearer challenges."""

from http import HTTPStatus
from typing import Any

from inframeld_backend.shared.http.definitions.problem_catalogue import (
    INVALID_AUTHENTICATION_REQUEST_PROBLEM,
)
from inframeld_backend.shared.http.mappers.problem_mapper import for_http_status
from inframeld_backend.shared.http.openapi.problem_openapi import problem_responses


def human_authentication_responses() -> dict[int | str, dict[str, Any]]:
    """Declare framework response mappings; challenge values come from the HTTP adapter."""
    responses = problem_responses(INVALID_AUTHENTICATION_REQUEST_PROBLEM) | problem_responses(
        for_http_status(HTTPStatus.UNAUTHORIZED)
    )
    for response in responses.values():
        response["headers"] = {
            "WWW-Authenticate": {
                "description": "Trusted Bearer challenge when applicable.",
                "schema": {"type": "string"},
            }
        }
    return responses
