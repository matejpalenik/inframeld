"""Provide a logging scope for an explicitly invoked application command.

The logging scope adds command metadata to Structlog's request-local context,
measures how long the command takes, and records expected and unexpected
failures. It does not dispatch commands or contain business logic; the caller
still invokes the appropriate application handler directly.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from time import perf_counter

import structlog
from structlog.contextvars import bound_contextvars

from inframeld_backend.shared.application.application_error import ApplicationError
from inframeld_backend.shared.application.command_context import CommandContext
from inframeld_backend.shared.infrastructure.timing import elapsed_milliseconds

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def command_logging_scope(context: CommandContext) -> AsyncGenerator[None]:
    """Add command context and log failures during one command execution.

    Args:
        context: Identifies the command and its operation for log correlation.

    Yields:
        Control to the application handler executing the command.

    Raises:
        ApplicationError: Re-raised after being logged as an expected failure.
        Exception: Re-raised after being logged as an unexpected failure.
    """

    # Start timing before entering the context so setup time is included.
    started_at = perf_counter()

    # These values are automatically included in log entries emitted inside
    # the scope, including logs from the application handler.
    with bound_contextvars(
        request_id=context.request_id,
        operation_id=context.operation_id,
        command_name=context.command_name,
    ):
        try:
            # The caller's ``async with`` block runs at this point.
            yield
        except ApplicationError as error:
            # Expected failures are useful operational events, but do not need
            # an unexpected-exception traceback.
            logger.warning(
                "command_failed",
                failure_kind="expected",
                error_code=error.code,
                duration_ms=elapsed_milliseconds(started_at),
            )
            raise
        except Exception:
            # Unknown failures include their traceback for diagnosis.
            logger.exception(
                "command_failed",
                failure_kind="unexpected",
                duration_ms=elapsed_milliseconds(started_at),
            )
            raise
        else:
            logger.info("command_completed", duration_ms=elapsed_milliseconds(started_at))
