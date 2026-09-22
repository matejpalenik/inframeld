"""Configure bounded, secret-safe structured logging."""

import json
import logging
import sys
from itertools import islice
from traceback import walk_tb
from types import TracebackType
from typing import cast

import structlog
from structlog.typing import EventDict, ExcInfo, Processor

from inframeld_backend.shared.infrastructure.error_reporting import is_error_reported
from inframeld_backend.shared.infrastructure.settings import LogFormat, LogLevel

_MAX_EXCEPTION_FRAMES = 20
_MAX_EXCEPTION_DEPTH = 5
_MAX_EXCEPTION_GROUP_CHILDREN = 8
_MAX_EXCEPTION_NODES = 16

_SAFE_EXCEPTION_ATTRIBUTE = "_inframeld_safe_exception"


def _logging_level(level: LogLevel) -> int:
    """Translate an application log level into its standard-library value."""
    return logging.getLevelNamesMapping()[level]


def _safe_exception_frames(
    traceback_value: TracebackType | None,
) -> tuple[list[dict[str, object]], bool]:
    """Extract bounded code locations without locals or source text.

    Args:
        traceback_value: Traceback whose frame locations should be recorded.

    Returns:
        The safe frame descriptions and whether additional frames were omitted.
    """
    captured = list(
        islice(
            walk_tb(traceback_value),
            _MAX_EXCEPTION_FRAMES + 1,
        )
    )

    frames: list[dict[str, object]] = []

    for frame, line_number in captured[:_MAX_EXCEPTION_FRAMES]:
        frames.append(
            {
                "filename": frame.f_code.co_filename,
                "function": frame.f_code.co_name,
                "lineno": line_number,
            }
        )

    return frames, len(captured) > _MAX_EXCEPTION_FRAMES


def _safe_exception_diagnostic(exc_info: ExcInfo) -> dict[str, object]:
    """Build a bounded diagnostic containing only reviewed structural data.

    Exception messages, notes, local variables, source lines, and arbitrary
    object representations are deliberately never inspected or serialized.

    Args:
        exc_info: Exception information supplied by Structlog.

    Returns:
        A JSON-serializable diagnostic containing exception types, bounded
        frame locations, and bounded cause, context, and group relationships.
    """
    _, root_error, root_traceback = exc_info

    remaining_nodes = _MAX_EXCEPTION_NODES
    seen: set[int] = set()

    def visit(
        error: BaseException,
        traceback_value: TracebackType | None,
        depth: int,
    ) -> dict[str, object]:
        """Visit one exception without reading user-authored exception text."""
        nonlocal remaining_nodes

        if depth >= _MAX_EXCEPTION_DEPTH or remaining_nodes == 0:
            return {"truncated": True}

        error_identity = id(error)

        if error_identity in seen:
            return {"cycle": True}

        seen.add(error_identity)
        remaining_nodes -= 1

        frames, frames_truncated = _safe_exception_frames(traceback_value)

        node: dict[str, object] = {
            "type": type(error).__name__,
            "frames": frames,
        }

        if frames_truncated:
            node["frames_truncated"] = True

        cause = error.__cause__
        context = error.__context__

        if cause is not None:
            node["cause"] = visit(
                cause,
                cause.__traceback__,
                depth + 1,
            )
        elif context is not None and not error.__suppress_context__:
            node["context"] = visit(
                context,
                context.__traceback__,
                depth + 1,
            )

        if isinstance(error, BaseExceptionGroup):
            # isinstance() proves the runtime type, but Pyright cannot infer
            # BaseExceptionGroup's generic exception parameter.
            group_error = cast(BaseExceptionGroup[BaseException], error)
            group_exceptions = group_error.exceptions
            children = group_exceptions[:_MAX_EXCEPTION_GROUP_CHILDREN]

            node["exceptions"] = [
                visit(
                    child,
                    child.__traceback__,
                    depth + 1,
                )
                for child in children
            ]

            omitted_children = len(group_exceptions) - len(children)

            if omitted_children:
                node["exceptions_truncated"] = omitted_children

        return node

    return visit(
        root_error,
        root_traceback,
        depth=0,
    )


def _normalize_stdlib_exc_info(value: object) -> ExcInfo | None:
    """Convert valid stdlib exception data into Structlog's typed form."""
    if not isinstance(value, tuple):
        return None

    parts = cast(tuple[object, ...], value)

    if len(parts) != 3:
        return None

    error_candidate = parts[1]
    traceback_candidate = parts[2]

    if not isinstance(error_candidate, BaseException):
        return None

    traceback_value: TracebackType | None

    if traceback_candidate is None:
        traceback_value = None
    elif isinstance(traceback_candidate, TracebackType):
        traceback_value = traceback_candidate
    else:
        return None

    exception_type: type[BaseException] = type(error_candidate)

    return (
        exception_type,
        error_candidate,
        traceback_value,
    )


class _ReportedUvicornExceptionFilter(logging.Filter):
    """Suppress only Uvicorn's duplicate report of an exact known exception."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Keep ordinary and unreported Uvicorn records."""
        exc_info = _normalize_stdlib_exc_info(record.exc_info)

        if exc_info is None:
            return True

        _, error, _ = exc_info

        return not is_error_reported(error)


_REPORTED_UVICORN_EXCEPTION_FILTER = _ReportedUvicornExceptionFilter()


class _SafeExceptionFilter(logging.Filter):
    """Replace raw stdlib exception state with a safe diagnostic."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Sanitize exception information on the original shared record."""
        exc_info = _normalize_stdlib_exc_info(record.exc_info)

        if exc_info is not None:
            diagnostic = _safe_exception_diagnostic(exc_info)
            setattr(record, _SAFE_EXCEPTION_ATTRIBUTE, diagnostic)

        # A later handler must never be able to render the raw exception or
        # reuse exception text cached by an earlier formatter.
        record.exc_info = None
        record.exc_text = None

        return True


def _merge_safe_stdlib_exception(
    _logger: object,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Copy a pre-sanitized stdlib diagnostic into the Structlog event.

    Args:
        event_dict: Event created by ``ProcessorFormatter`` from a LogRecord.

    Returns:
        The event containing the safe diagnostic when one was attached.
    """
    record: object | None = event_dict.get("_record")

    if not isinstance(record, logging.LogRecord):
        return event_dict

    diagnostic: object | None = getattr(
        record,
        _SAFE_EXCEPTION_ATTRIBUTE,
        None,
    )

    if diagnostic is not None:
        event_dict["exception"] = diagnostic

    return event_dict


def _format_safe_exception_for_console(
    _logger: object,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Render the already-sanitized diagnostic for console output.

    Args:
        event_dict: Processed event containing no raw exception information.

    Returns:
        The event with its safe diagnostic converted to readable JSON text.
    """
    diagnostic: object | None = event_dict.get("exception")

    if diagnostic is not None:
        event_dict["exception"] = json.dumps(
            diagnostic,
            indent=2,
            sort_keys=True,
        )

    return event_dict


def configure_logging(*, level: LogLevel, log_format: LogFormat) -> None:
    """Configure Structlog and standard-library logging.

    Args:
        level: Minimum application logging level.
        log_format: Final JSON or developer-console representation.
    """
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    exception_processor: Processor = structlog.processors.ExceptionRenderer(
        _safe_exception_diagnostic
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
        _merge_safe_stdlib_exception,
        exception_processor,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.CallsiteParameterAdder(
            {
                structlog.processors.CallsiteParameter.FILENAME,
                structlog.processors.CallsiteParameter.FUNC_NAME,
                structlog.processors.CallsiteParameter.LINENO,
            }
        ),
    ]

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    renderer_processors: list[Processor] = [
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
    ]

    if log_format == "json":
        renderer_processors.append(structlog.processors.JSONRenderer())
    else:
        renderer_processors.extend(
            [
                _format_safe_exception_for_console,
                structlog.dev.ConsoleRenderer(),
            ]
        )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=renderer_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(_SafeExceptionFilter())
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(_logging_level(level))

    # Route Uvicorn's standard-library logs through the same formatter.
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)

    # Uvicorn may log an exception that the application boundary already
    # reported. Suppress only that exact exception instance. This logger-level
    # filter runs before the root handler clears raw exception information.
    logging.getLogger("uvicorn.error").addFilter(_REPORTED_UVICORN_EXCEPTION_FILTER)

    # RequestContextMiddleware is the canonical access logger.
    logging.getLogger("uvicorn.access").disabled = True
