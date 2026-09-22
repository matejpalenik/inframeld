"""Verify that request logs do not expose raw URL paths."""

import asyncio
import json
from typing import cast

import httpx2
import pytest
import structlog
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

from inframeld_backend.shared.http.error_handlers import register_error_handlers
from inframeld_backend.shared.http.request_context import RequestContextMiddleware
from inframeld_backend.shared.infrastructure.logging import configure_logging

SECRET = "synthetic-private-path-value"


def _create_app() -> FastAPI:
    """Create routes that expose request context in application logs."""
    app = FastAPI(debug=False)
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    @app.get("/_test/resources/{resource_id}")
    async def get_resource(resource_id: str) -> dict[str, bool]:
        structlog.get_logger(__name__).info("inside_resource_route")
        return {"found": bool(resource_id)}

    return app


def test_request_logs_use_route_template_without_raw_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep path values out of logs for matched and unmatched requests."""
    configure_logging(level="INFO", log_format="json")

    with TestClient(_create_app()) as client:
        matched = client.get(f"/_test/resources/{SECRET}")
        missing = client.get(f"/_test/unknown/{SECRET}")

    assert matched.status_code == 200
    assert missing.status_code == 404

    events = [
        cast(dict[str, object], json.loads(line))
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]
    application_events = [
        event
        for event in events
        if event.get("event") in {"inside_resource_route", "request_completed"}
    ]

    assert len(application_events) == 3
    assert SECRET not in json.dumps(application_events)
    assert all("http_path" not in event for event in application_events)

    matched_completion = next(
        event
        for event in application_events
        if event.get("event") == "request_completed"
        and event.get("request_id") == matched.headers["x-request-id"]
    )
    missing_completion = next(
        event
        for event in application_events
        if event.get("event") == "request_completed"
        and event.get("request_id") == missing.headers["x-request-id"]
    )

    assert matched_completion["http_route"] == "/_test/resources/{resource_id}"
    assert "http_route" not in missing_completion


@pytest.mark.asyncio
async def test_overlapping_requests_keep_distinct_log_context(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Correlate sync and async dependency logs with the correct request."""
    configure_logging(level="INFO", log_format="json")

    app = FastAPI(debug=False)
    register_error_handlers(app)
    app.add_middleware(RequestContextMiddleware)

    both_arrived = asyncio.Event()
    arrivals = 0
    probe_logger = structlog.get_logger(__name__)

    def sync_probe() -> None:
        """Log from FastAPI's dependency thread pool."""
        probe_logger.info("sync_probe")

    async def async_probe() -> None:
        """Hold both requests open together before logging."""
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            both_arrived.set()

        await both_arrived.wait()
        probe_logger.info("async_probe")

    @app.get(
        "/_test/context",
        dependencies=[Depends(sync_probe), Depends(async_probe)],
    )
    async def context_probe() -> dict[str, bool]:
        return {"ok": True}

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first, second = await asyncio.wait_for(
            asyncio.gather(
                client.get("/_test/context"),
                client.get("/_test/context"),
            ),
            timeout=5.0,
        )

    assert first.status_code == second.status_code == 200
    request_ids = {
        first.headers["x-request-id"],
        second.headers["x-request-id"],
    }
    assert len(request_ids) == 2

    events = [
        cast(dict[str, object], json.loads(line))
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]
    relevant_events = [
        event
        for event in events
        if event.get("event") in {"sync_probe", "async_probe", "request_completed"}
    ]

    assert len(relevant_events) == 6

    for request_id in request_ids:
        associated = [event for event in relevant_events if event.get("request_id") == request_id]
        assert sum(event.get("event") == "sync_probe" for event in associated) == 1
        assert sum(event.get("event") == "async_probe" for event in associated) == 1
        assert sum(event.get("event") == "request_completed" for event in associated) == 1


@pytest.mark.asyncio
async def test_late_failure_reports_status_without_starting_another_response(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Record a failure after headers are sent without replacing the response."""
    configure_logging(level="INFO", log_format="json")
    sent: list[Message] = []

    async def failing_app(_scope: Scope, _receive: Receive, send: Send) -> None:
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"first chunk", "more_body": True})
        raise RuntimeError(SECRET)

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def capture_send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "path": "/_test/stream"}

    with pytest.raises(RuntimeError, match=SECRET):
        await RequestContextMiddleware(failing_app)(scope, receive, capture_send)

    assert [message["type"] for message in sent] == [
        "http.response.start",
        "http.response.body",
    ]
    assert sent[0]["status"] == 200
    request_id = dict(sent[0]["headers"])[b"x-request-id"].decode("ascii")

    events = [
        cast(dict[str, object], json.loads(line))
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]
    failures = [event for event in events if event.get("event") == "request_failed"]

    assert len(failures) == 1
    assert failures[0]["request_id"] == request_id
    assert failures[0]["status_code"] == 200
    assert SECRET not in json.dumps(failures)


@pytest.mark.asyncio
async def test_cancelled_request_does_not_send_or_report_a_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Let cancellation propagate without fabricating an HTTP failure."""
    configure_logging(level="INFO", log_format="json")
    started = asyncio.Event()
    blocked = asyncio.Event()
    sent: list[Message] = []

    async def waiting_app(_scope: Scope, _receive: Receive, _send: Send) -> None:
        started.set()
        await blocked.wait()

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def capture_send(message: Message) -> None:
        sent.append(message)

    scope: Scope = {"type": "http", "method": "GET", "path": "/_test/slow"}
    task = asyncio.create_task(RequestContextMiddleware(waiting_app)(scope, receive, capture_send))

    await asyncio.wait_for(started.wait(), timeout=2.0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert sent == []

    events = [
        cast(dict[str, object], json.loads(line))
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]
    assert not any(
        event.get("event") in {"request_failed", "request_completed"} for event in events
    )
