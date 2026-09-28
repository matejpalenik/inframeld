"""Verify HTTP idempotency keys become typed application values."""

from typing import Annotated

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.http.dependencies.idempotency_key_dependency import (
    IdempotencyKeyDependency,
)
from inframeld_backend.shared.http.handlers.error_handlers import register_error_handlers
from inframeld_backend.shared.http.middleware.request_context_middleware import (
    RequestContextMiddleware,
)


def _test_app(seen: list[IdempotencyKey]) -> FastAPI:
    application = FastAPI(debug=False)
    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)
    key_dependency = IdempotencyKeyDependency()

    @application.post("/_test/command")
    async def command(
        key: Annotated[IdempotencyKey, Depends(key_dependency)],
    ) -> dict[str, bool]:
        seen.append(key)
        return {"accepted": True}

    @application.get("/_test/read")
    async def read() -> dict[str, bool]:
        return {"ok": True}

    return application


def test_valid_header_supplies_a_typed_key() -> None:
    seen: list[IdempotencyKey] = []

    with TestClient(_test_app(seen), raise_server_exceptions=False) as client:
        response = client.post(
            "/_test/command",
            headers={"Idempotency-Key": "build-request-1"},
        )

    assert response.status_code == 200
    assert seen == [IdempotencyKey("build-request-1")]


def test_missing_header_is_rejected() -> None:
    seen: list[IdempotencyKey] = []

    with TestClient(_test_app(seen), raise_server_exceptions=False) as client:
        response = client.post("/_test/command")

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert seen == []


@pytest.mark.parametrize("value", ["   ", "x" * 129])
def test_invalid_header_is_rejected_without_running_the_command(value: str) -> None:
    seen: list[IdempotencyKey] = []

    with TestClient(_test_app(seen), raise_server_exceptions=False) as client:
        response = client.post(
            "/_test/command",
            headers={"Idempotency-Key": value},
        )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"
    assert value not in response.text
    assert seen == []


def test_duplicate_headers_are_rejected() -> None:
    seen: list[IdempotencyKey] = []

    with TestClient(_test_app(seen), raise_server_exceptions=False) as client:
        response = client.post(
            "/_test/command",
            headers=[
                ("Idempotency-Key", "first"),
                ("Idempotency-Key", "second"),
            ],
        )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_input"
    assert seen == []


def test_read_route_does_not_require_a_key() -> None:
    seen: list[IdempotencyKey] = []

    with TestClient(_test_app(seen)) as client:
        response = client.get("/_test/read")

    assert response.status_code == 200
    assert response.json() == {"ok": True}
