"""Check the shared pagination query contract through HTTP."""

from typing import Annotated

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient

from inframeld_backend.shared.http.error_handlers import register_error_handlers
from inframeld_backend.shared.http.pagination import PaginationQuery
from inframeld_backend.shared.http.request_context import RequestContextMiddleware


def _fixture_app() -> FastAPI:
    """Expose pagination through a test-only route."""
    application = FastAPI()
    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)

    @application.get("/fixture/items")
    async def list_items(
        pagination: Annotated[PaginationQuery, Query()],
    ) -> dict[str, int | str | None]:
        return {"limit": pagination.limit, "cursor": pagination.cursor}

    return application


def test_omitted_limit_defaults_to_25() -> None:
    """A client can request the first page without choosing a size."""
    with TestClient(_fixture_app()) as client:
        response = client.get("/fixture/items")

    assert response.status_code == 200
    assert response.json()["limit"] == 25


@pytest.mark.parametrize("limit", [0, -1, 101, "not-a-number"])
def test_invalid_limit_returns_validation_problem(limit: int | str) -> None:
    """Reject zero, negative, oversized, and nonnumeric page sizes."""
    with TestClient(_fixture_app()) as client:
        response = client.get("/fixture/items", params={"limit": limit})

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["code"] == "validation_error"


@pytest.mark.parametrize("limit", [0, -1, 101])
def test_out_of_range_limit_identifies_the_query_parameter(limit: int) -> None:
    """Tell clients which limit field failed at either bound."""
    with TestClient(_fixture_app()) as client:
        response = client.get("/fixture/items", params={"limit": limit})

    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "location": "query",
            "path": ["limit"],
            "code": "out_of_range",
            "message": "Use a value within the permitted range.",
        }
    ]


@pytest.mark.parametrize("limit", [1, 100])
def test_limit_accepts_inclusive_boundaries(limit: int) -> None:
    """Allow both the smallest and largest permitted page sizes."""
    with TestClient(_fixture_app()) as client:
        response = client.get("/fixture/items", params={"limit": limit})

    assert response.status_code == 200
    assert response.json()["limit"] == limit


@pytest.mark.parametrize("cursor", ["", "bad%cursor", "x" * 1025])
def test_malformed_cursor_returns_validation_problem(cursor: str) -> None:
    """Reject empty, invalid-character, and oversized cursor tokens."""
    with TestClient(_fixture_app()) as client:
        response = client.get("/fixture/items", params={"cursor": cursor})

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
