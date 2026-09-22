"""Verify diagnostic ownership across command and HTTP boundaries."""

import json
import logging
from typing import cast

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from inframeld_backend.shared.application.application_error import ApplicationError
from inframeld_backend.shared.application.command_context import (
    CommandContext,
    OperationId,
    RequestId,
)
from inframeld_backend.shared.application.errors import DependencyUnavailableError
from inframeld_backend.shared.http.error_handlers import register_error_handlers
from inframeld_backend.shared.http.request_context import RequestContextMiddleware
from inframeld_backend.shared.infrastructure.command_logging import (
    command_logging_scope,
)
from inframeld_backend.shared.infrastructure.error_reporting import report_unexpected_error
from inframeld_backend.shared.infrastructure.logging import configure_logging

SECRET = "synthetic-command-secret"
OPERATION_ID = OperationId("synthetic-operation-id")
COMMAND_NAME = "synthetic_command"


class _UnregisteredApplicationError(ApplicationError):
    """Represent an application failure with no reviewed public mapping."""


def _create_nested_failure_app() -> FastAPI:
    """Create an app whose failing route enters the real command scope."""
    application = FastAPI(debug=False)

    register_error_handlers(application)
    application.add_middleware(RequestContextMiddleware)

    @application.get("/_test/command-runtime-error")
    async def command_runtime_error(request: Request) -> None:
        raw_request_id = cast(
            object,
            request.state.request_id,
        )

        if not isinstance(raw_request_id, str):
            raise AssertionError("Request middleware did not provide an ID.")

        context = CommandContext(
            request_id=RequestId(raw_request_id),
            operation_id=OPERATION_ID,
            command_name=COMMAND_NAME,
        )

        async with command_logging_scope(context):
            raise RuntimeError(SECRET)

    @application.get("/_test/unregistered-application-error")
    async def unregistered_application_error() -> None:
        raise _UnregisteredApplicationError(SECRET)

    @application.get("/_test/dependency-unavailable-with-cause")
    async def dependency_unavailable_with_cause() -> None:
        try:
            raise RuntimeError(SECRET)
        except RuntimeError as cause:
            raise DependencyUnavailableError(SECRET) from cause

    @application.get("/_test/dependency-unavailable-without-cause")
    async def dependency_unavailable_without_cause() -> None:
        raise DependencyUnavailableError(SECRET)

    return application


def _create_outer_handler_only_app() -> FastAPI:
    """Create an app where only the outer error handler can report failures."""
    application = FastAPI(debug=False)

    # There is deliberately no RequestContextMiddleware
    # this reproduces an exception that reaches the outer handler
    # without having been reported.
    register_error_handlers(application)

    @application.get("/_test/runtime-error")
    async def runtime_error() -> None:
        raise RuntimeError(SECRET)

    return application


def _captured_runtime_error(message: str) -> RuntimeError:
    """Create a runtime error carrying a real traceback."""
    try:
        raise RuntimeError(message)
    except RuntimeError as error:
        return error


def test_request_boundary_owns_nested_command_diagnostic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Record one command outcome and one request-owned diagnostic."""
    configure_logging(level="INFO", log_format="json")
    application = _create_nested_failure_app()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/_test/command-runtime-error")

    assert response.status_code == 500

    rendered = capsys.readouterr().out
    events = [
        cast(dict[str, object], json.loads(line)) for line in rendered.splitlines() if line.strip()
    ]

    command_events = [event for event in events if event.get("event") == "command_failed"]
    request_events = [event for event in events if event.get("event") == "request_failed"]

    assert len(command_events) == 1
    assert len(request_events) == 1

    command_event = command_events[0]
    request_event = request_events[0]
    request_id = response.headers["x-request-id"]

    assert command_event["failure_kind"] == "unexpected"
    assert command_event["operation_id"] == OPERATION_ID
    assert command_event["command_name"] == COMMAND_NAME
    assert command_event["request_id"] == request_id
    assert "exception" not in command_event

    assert request_event["request_id"] == request_id
    assert "exception" in request_event

    diagnostic_events = [event for event in events if "exception" in event]

    assert len(diagnostic_events) == 1
    assert SECRET not in rendered


def test_unregistered_application_error_receives_unexpected_diagnostic(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report an unmapped handled application failure exactly once."""
    configure_logging(level="INFO", log_format="json")
    application = _create_nested_failure_app()

    with TestClient(application) as client:
        response = client.get("/_test/unregistered-application-error")

    assert response.status_code == 500

    rendered = capsys.readouterr().out
    events = [
        cast(dict[str, object], json.loads(line)) for line in rendered.splitlines() if line.strip()
    ]

    diagnostic_events = [event for event in events if "exception" in event]

    assert len(diagnostic_events) == 1

    diagnostic_event = diagnostic_events[0]
    request_id = response.headers["x-request-id"]

    assert diagnostic_event["event"] == "request_failed"
    assert diagnostic_event["request_id"] == request_id
    assert "_UnregisteredApplicationError" in rendered
    assert SECRET not in rendered


def test_same_exception_instance_is_reported_only_once(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Suppress duplicate diagnostics only for the exact reported exception."""
    configure_logging(level="INFO", log_format="json")

    reported_error = RuntimeError(SECRET)
    separate_error = RuntimeError(SECRET)

    report_unexpected_error(
        reported_error,
        event="first_boundary_failed",
    )
    report_unexpected_error(
        reported_error,
        event="outer_boundary_failed",
    )
    report_unexpected_error(
        separate_error,
        event="separate_failure",
    )

    rendered = capsys.readouterr().out
    events = [
        cast(dict[str, object], json.loads(line)) for line in rendered.splitlines() if line.strip()
    ]
    diagnostic_events = [event for event in events if "exception" in event]

    assert [event["event"] for event in diagnostic_events] == [
        "first_boundary_failed",
        "separate_failure",
    ]
    assert SECRET not in rendered


def test_outer_handler_reports_unreported_error_with_response_request_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Correlate an outer-handler diagnostic with its safe 500 response."""
    configure_logging(level="INFO", log_format="json")
    application = _create_outer_handler_only_app()

    with TestClient(application, raise_server_exceptions=False) as client:
        response = client.get("/_test/runtime-error")

    assert response.status_code == 500

    rendered = capsys.readouterr().out
    events = [
        cast(dict[str, object], json.loads(line)) for line in rendered.splitlines() if line.strip()
    ]
    diagnostic_events = [event for event in events if "exception" in event]

    assert len(diagnostic_events) == 1

    diagnostic_event = diagnostic_events[0]

    assert diagnostic_event["event"] == "request_failed"
    assert diagnostic_event["request_id"] == response.headers["x-request-id"]
    assert SECRET not in rendered


def test_dependency_failure_is_reported_only_when_cause_is_available(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Report one actionable dependency diagnostic when a cause exists."""
    configure_logging(level="INFO", log_format="json")
    application = _create_nested_failure_app()

    with TestClient(application) as client:
        caused_response = client.get("/_test/dependency-unavailable-with-cause")
        uncaused_response = client.get("/_test/dependency-unavailable-without-cause")

    assert caused_response.status_code == 503
    assert uncaused_response.status_code == 503

    rendered = capsys.readouterr().out
    events = [
        cast(dict[str, object], json.loads(line)) for line in rendered.splitlines() if line.strip()
    ]
    diagnostic_events = [event for event in events if "exception" in event]

    assert len(diagnostic_events) == 1

    diagnostic_event = diagnostic_events[0]

    assert diagnostic_event["event"] == "request_failed"
    assert diagnostic_event["error_code"] == "dependency_unavailable"
    assert diagnostic_event["request_id"] == caused_response.headers["x-request-id"]
    assert diagnostic_event["request_id"] != uncaused_response.headers["x-request-id"]
    assert "DependencyUnavailableError" in rendered
    assert SECRET not in rendered


def test_uvicorn_suppresses_only_the_exact_reported_exception(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Keep Uvicorn logs except for an already-reported exception instance."""
    configure_logging(level="INFO", log_format="json")

    reported_error = _captured_runtime_error(SECRET)
    unreported_error = _captured_runtime_error(SECRET)

    report_unexpected_error(
        reported_error,
        event="request_failed",
    )

    uvicorn_logger = logging.getLogger("uvicorn.error")

    uvicorn_logger.error(
        "duplicate_uvicorn_failure",
        exc_info=(
            type(reported_error),
            reported_error,
            reported_error.__traceback__,
        ),
    )
    uvicorn_logger.error(
        "unreported_uvicorn_failure",
        exc_info=(
            type(unreported_error),
            unreported_error,
            unreported_error.__traceback__,
        ),
    )
    uvicorn_logger.info("uvicorn_server_message")

    rendered = capsys.readouterr().out
    events = [
        cast(dict[str, object], json.loads(line)) for line in rendered.splitlines() if line.strip()
    ]
    event_names = [event.get("event") for event in events]

    assert event_names.count("request_failed") == 1
    assert "duplicate_uvicorn_failure" not in event_names
    assert "unreported_uvicorn_failure" in event_names
    assert "uvicorn_server_message" in event_names

    unreported_event = next(
        event for event in events if event.get("event") == "unreported_uvicorn_failure"
    )

    assert "exception" in unreported_event
    assert SECRET not in rendered
