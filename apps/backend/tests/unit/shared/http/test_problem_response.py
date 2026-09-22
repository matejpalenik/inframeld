"""Verify construction of RFC 9457 HTTP responses."""

import json
from uuid import UUID

import pytest
from starlette.requests import Request
from starlette.types import Scope

from inframeld_backend.shared.http.problem_definitions import (
    CONFLICT_PROBLEM,
    DEPENDENCY_UNAVAILABLE_PROBLEM,
    VALIDATION_ERROR_PROBLEM,
)
from inframeld_backend.shared.http.problem_response import build_problem_response
from inframeld_backend.shared.http.problems import ValidationIssue

REQUEST_ID = "c66a2044-4e4f-4c07-983e-a3c221c7b1ad"


def _request(*, request_id: str | None = REQUEST_ID, method: str = "GET") -> Request:
    """Create a synthetic request with optional middleware correlation state."""
    state: dict[str, object] = {}
    if request_id is not None:
        state["request_id"] = request_id

    scope: Scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": "/synthetic",
        "raw_path": b"/synthetic",
        "query_string": b"",
        "root_path": "",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "state": state,
    }
    return Request(scope)


def test_builds_problem_response_from_reviewed_definition() -> None:
    """Use one definition consistently across status, headers, and body."""
    response = build_problem_response(_request(), CONFLICT_PROBLEM)

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"] == REQUEST_ID
    assert json.loads(bytes(response.body)) == {
        "type": (
            "https://github.com/matejpalenik/inframeld/blob/main/"
            "docs/development/error-handling.md#conflict"
        ),
        "title": "Operation conflicts with current state",
        "status": 409,
        "detail": "The operation cannot be completed in the current state.",
        "code": "conflict",
        "requestId": REQUEST_ID,
    }


def test_generates_request_id_when_context_state_is_missing() -> None:
    """Generate and store correlation when middleware state is unavailable."""

    request = _request(request_id=None)

    response = build_problem_response(request, CONFLICT_PROBLEM)

    result = json.loads(bytes(response.body))

    generated_id = response.headers["x-request-id"]

    assert str(UUID(generated_id)) == generated_id
    assert result["requestId"] == generated_id
    assert request.state.request_id == generated_id


def test_preserves_supported_protocol_headers_without_overriding_problem_headers() -> None:
    """Preserve reviewed protocol headers while enforcing problem invariants."""

    response = build_problem_response(
        _request(),
        DEPENDENCY_UNAVAILABLE_PROBLEM,
        protocol_headers={
            "Retry-After": "120",
            "Cache-Control": "public",
            "Content-Type": "text/plain",
            "X-Request-ID": "caller-controlled",
            "X-Unreviewed": "must-not-be-forwarded",
        },
    )

    assert response.headers.get("retry-after") == "120"
    assert response.headers.get("cache-control") == "no-store"
    assert response.headers.get("content-type") == "application/problem+json"
    assert response.headers.get("x-request-id") == REQUEST_ID
    assert "x-unreviewed" not in response.headers


def test_requires_at_least_one_issue_for_validation_problem() -> None:
    """Reject an invalid validation problem with no field issues."""

    with pytest.raises(ValueError, match="Validation problems require at least one issue"):
        build_problem_response(_request(), VALIDATION_ERROR_PROBLEM)


def test_rejects_validation_issues_for_other_problem_types() -> None:
    """Reject validation extensions on an unrelated problem type."""

    issue = ValidationIssue(
        location="body", path=("name",), code="invalid_value", message="Use a valid value."
    )

    with pytest.raises(ValueError, match="Only validation problems may include validation issues"):
        build_problem_response(_request(), CONFLICT_PROBLEM, errors=(issue,))


def test_omits_problem_body_for_head_request() -> None:
    """Return problem headers and status without a body for HEAD."""

    response = build_problem_response(_request(method="HEAD"), CONFLICT_PROBLEM)

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"] == REQUEST_ID
    assert bytes(response.body) == b""
