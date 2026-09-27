"""Verify errors produced through the real FastAPI request boundary."""

from typing import Annotated
from uuid import UUID

import pytest
from fastapi import FastAPI, HTTPException, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from inframeld_backend.shared.application.errors.application_error import (
    ApplicationError,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    IdempotencyInProgressError,
    IdempotencyKeyReusedError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.errors.domain_errors import DomainError
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)

SECRET = "synthetic-secret-value"
VALIDATION_TYPE = (
    "https://github.com/matejpalenik/inframeld/blob/main/"
    "docs/development/error-handling.md#validation-error"
)

CONFLICT_TYPE = (
    "https://github.com/matejpalenik/inframeld/blob/main/"
    "docs/development/error-handling.md#conflict"
)
INTERNAL_TYPE = (
    "https://github.com/matejpalenik/inframeld/blob/main/"
    "docs/development/error-handling.md#internal-error"
)


class _UnregisteredApplicationError(ApplicationError):
    """Represent an application failure with no reviewed HTTP mapping."""


class _IntegerResponse(BaseModel):
    """Define the response contract used to trigger response validation."""

    value: int


def _create_error_test_app() -> FastAPI:
    """Create a test-only app using the production middleware and handlers."""
    application = FastAPI(debug=False)

    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)

    @application.get("/_test/items")
    async def list_items(
        limit: Annotated[int, Query(ge=1, le=100)],
    ) -> dict[str, int]:
        """Expose parsed query inputs for validation-problem assertions."""
        return {"limit": limit}

    @application.get("/_test/conflict")
    async def conflict() -> None:
        """Raise an application conflict whose private text must stay out of the response."""
        raise ConflictError(SECRET)

    @application.post("/_test/idempotency-key-reused")
    async def idempotency_key_reused() -> None:
        raise IdempotencyKeyReusedError(SECRET)

    @application.post("/_test/idempotency-in-progress")
    async def idempotency_in_progress() -> None:
        raise IdempotencyInProgressError(
            operation_id=OperationId("original-operation-123"),
            retry_after_seconds=3,
            message=SECRET,
        )

    @application.get("/_test/authentication-required")
    async def authentication_required() -> None:
        """Exercise the generic HTTP authentication failure and allowed protocol headers."""
        raise HTTPException(
            status_code=401,
            detail=SECRET,
            headers={
                "WWW-Authenticate": 'Bearer realm="inframeld"',
                "X-Unreviewed": SECRET,
            },
        )

    @application.get("/_test/unregistered-application-error")
    async def unregistered_application_error() -> None:
        """Exercise fail-closed mapping for an unknown application error subtype."""
        raise _UnregisteredApplicationError(SECRET)

    @application.get("/_test/domain-error")
    async def domain_error() -> None:
        """Ensure a domain exception cannot leak its private text through HTTP."""
        raise DomainError(SECRET)

    @application.get("/_test/runtime-error")
    async def runtime_error() -> None:
        """Raise an unexpected failure to verify the generic internal problem."""
        raise RuntimeError(SECRET)

    @application.get("/_test/invalid-response", response_model=_IntegerResponse)
    async def invalid_response() -> dict[str, str]:
        """Return invalid data to verify response-validation failures are treated as internal errors."""
        return {"value": SECRET}

    return application


def test_request_validation_uses_safe_correlated_problem() -> None:
    """Return a sanitized RFC 9457 problem for malformed query input."""
    application = _create_error_test_app()

    with TestClient(application) as client:
        response = client.get("/_test/items", params={"limit": SECRET})

    body: dict[str, object] = response.json()
    request_id = response.headers["x-request-id"]

    assert str(UUID(request_id)) == request_id
    assert response.status_code == body["status"] == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"

    assert body == {
        "type": VALIDATION_TYPE,
        "title": "Request validation failed",
        "status": 422,
        "detail": "One or more request fields are invalid.",
        "code": "validation_error",
        "requestId": request_id,
        "errors": [
            {
                "location": "query",
                "path": ["limit"],
                "code": "invalid_type",
                "message": "Use a value of the expected type.",
            }
        ],
    }

    assert SECRET not in response.text


def test_supported_application_error_uses_reviewed_problem() -> None:
    """Map a supported application failure without exposing its message."""
    application = _create_error_test_app()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/_test/conflict")

    # Assert before parsing because the current unhandled 500 response is not JSON.
    assert response.status_code == 409

    body: dict[str, object] = response.json()
    request_id = response.headers["x-request-id"]

    assert str(UUID(request_id)) == request_id
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"

    assert body == {
        "type": CONFLICT_TYPE,
        "title": "Operation conflicts with current state",
        "status": 409,
        "detail": "The operation cannot be completed in the current state.",
        "code": "conflict",
        "requestId": request_id,
    }

    assert SECRET not in response.text


def test_router_not_found_uses_generic_http_problem() -> None:
    """Normalize Starlette's router 404 into a correlated RFC 9457 problem."""
    application = _create_error_test_app()

    with TestClient(application) as client:
        response = client.get("/_test/does-not-exist")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"

    body: dict[str, object] = response.json()
    request_id = response.headers["x-request-id"]

    assert str(UUID(request_id)) == request_id
    assert body == {
        "type": "about:blank",
        "title": "Not Found",
        "status": 404,
        "detail": "The requested resource was not found.",
        "code": "http_error",
        "requestId": request_id,
    }


def test_method_not_allowed_preserves_allow_header() -> None:
    """Return a safe 405 problem while preserving Starlette's Allow header."""
    application = _create_error_test_app()

    with TestClient(application) as client:
        response = client.post("/_test/items")

    assert response.status_code == 405
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get("allow") == "GET"

    body: dict[str, object] = response.json()
    request_id = response.headers["x-request-id"]

    assert str(UUID(request_id)) == request_id
    assert body == {
        "type": "about:blank",
        "title": "Method Not Allowed",
        "status": 405,
        "detail": "The requested method is not allowed for this resource.",
        "code": "http_error",
        "requestId": request_id,
    }


def test_authentication_error_preserves_challenge_without_exposing_detail() -> None:
    """Preserve the 401 challenge without exposing unreviewed error data."""
    application = _create_error_test_app()

    with TestClient(application) as client:
        response = client.get("/_test/authentication-required")

    assert response.status_code == 401
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers.get("www-authenticate") == 'Bearer realm="inframeld"'
    assert "x-unreviewed" not in response.headers

    body: dict[str, object] = response.json()
    request_id = response.headers["x-request-id"]

    assert str(UUID(request_id)) == request_id
    assert body == {
        "type": "about:blank",
        "title": "Unauthorized",
        "status": 401,
        "detail": "Authentication is required.",
        "code": "http_error",
        "requestId": request_id,
    }

    assert SECRET not in response.text


@pytest.mark.parametrize(
    "path",
    [
        pytest.param(
            "/_test/unregistered-application-error",
            id="unregistered-application-error",
        ),
        pytest.param("/_test/domain-error", id="domain-error"),
        pytest.param("/_test/runtime-error", id="runtime-error"),
        pytest.param("/_test/invalid-response", id="invalid-response"),
    ],
)
def test_unexpected_failure_uses_safe_correlated_problem(path: str) -> None:
    """Normalize unsupported and internal failures without exposing details."""
    application = _create_error_test_app()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get(path)

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"

    body: dict[str, object] = response.json()
    request_id = response.headers["x-request-id"]

    assert str(UUID(request_id)) == request_id
    assert body == {
        "type": INTERNAL_TYPE,
        "title": "Internal server error",
        "status": 500,
        "detail": "An unexpected error occurred.",
        "code": "internal_error",
        "requestId": request_id,
    }

    assert SECRET not in response.text


def test_unexpected_failure_still_propagates_to_server() -> None:
    """Let the ASGI server observe an unexpected error after safe handling."""
    application = _create_error_test_app()

    with TestClient(application) as client, pytest.raises(RuntimeError, match=SECRET):
        client.get("/_test/runtime-error")


def test_idempotency_key_reuse_has_specific_safe_problem() -> None:
    application = _create_error_test_app()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post("/_test/idempotency-key-reused")

    assert response.status_code == 409

    body: dict[str, object] = response.json()
    assert body["code"] == "idempotency_key_reused"
    assert body["type"] == (
        "https://github.com/matejpalenik/inframeld/blob/main/"
        "docs/development/error-handling.md#idempotency-key-reused"
    )
    assert body["requestId"] == response.headers["x-request-id"]
    assert response.headers["content-type"] == "application/problem+json"
    assert SECRET not in response.text


def test_unfinished_retry_returns_original_operation_and_retry_hint() -> None:
    application = _create_error_test_app()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.post("/_test/idempotency-in-progress")

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["retry-after"] == "3"

    body: dict[str, object] = response.json()
    assert body == {
        "type": (
            "https://github.com/matejpalenik/inframeld/blob/main/"
            "docs/development/error-handling.md#idempotency-in-progress"
        ),
        "title": "Operation in progress",
        "status": 409,
        "detail": "The original request is still in progress.",
        "code": "idempotency_in_progress",
        "requestId": response.headers["x-request-id"],
        "operationId": "original-operation-123",
    }
    assert SECRET not in response.text
