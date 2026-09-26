"""Verify error reporting through Uvicorn's real HTTP protocol."""

import asyncio
import json
import os
from typing import cast

import httpx2
import pytest
import uvicorn
from fastapi import FastAPI

from inframeld_backend.shared.http.error_handlers import register_error_handlers
from inframeld_backend.shared.http.request_context import RequestContextMiddleware
from inframeld_backend.shared.infrastructure.logging import configure_logging

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run integration tests",
)

SECRET = "synthetic-uvicorn-secret"


def _failing_app() -> FastAPI:
    """Create a test-only app with a real unexpected HTTP failure."""
    app = FastAPI(debug=False)
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/_test/fail")
    async def fail() -> None:
        raise RuntimeError(SECRET)

    return app


@pytest.mark.asyncio
async def test_uvicorn_emits_one_diagnostic_for_failed_request(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Suppress Uvicorn's duplicate while preserving the safe 500 response."""
    configure_logging(level="INFO", log_format="json")

    server = uvicorn.Server(
        uvicorn.Config(
            _failing_app(),
            host="127.0.0.1",
            port=0,
            http="auto",
            lifespan="off",
            log_config=None,
            access_log=False,
        )
    )
    server_task = asyncio.create_task(server.serve())

    try:
        async with asyncio.timeout(10):
            while not server.started:
                if server_task.done():
                    await server_task
                    raise AssertionError("Uvicorn exited before starting.")
                await asyncio.sleep(0.01)

        sockets = server.servers[0].sockets
        assert sockets is not None
        port = cast(tuple[str, int], sockets[0].getsockname())[1]

        async with httpx2.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(f"http://127.0.0.1:{port}/_test/fail")
    finally:
        server.should_exit = True
        await asyncio.wait_for(server_task, timeout=10)

    assert response.status_code == 500
    assert response.headers["content-type"] == "application/problem+json"

    body = cast(dict[str, object], response.json())
    request_id = response.headers["x-request-id"]
    assert body["requestId"] == request_id

    rendered = capsys.readouterr().out
    events = [
        cast(dict[str, object], json.loads(line)) for line in rendered.splitlines() if line.strip()
    ]
    diagnostics = [event for event in events if "exception" in event]

    assert len(diagnostics) == 1
    assert diagnostics[0]["event"] == "request_failed"
    assert diagnostics[0]["request_id"] == request_id
    assert "Exception in ASGI application" not in rendered
    assert SECRET not in rendered
