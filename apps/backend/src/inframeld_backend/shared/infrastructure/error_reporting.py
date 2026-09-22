"""Provide safe reporting for unexpected failures at process boundaries."""

import structlog

logger = structlog.get_logger(__name__)

_REPORTED_ATTRIBUTE = "_inframeld_unexpected_error_reported"
_REPORTED_MARKER = object()


def is_error_reported(error: BaseException) -> bool:
    """Return whether this exact exception instance was already reported."""
    return getattr(error, _REPORTED_ATTRIBUTE, None) is _REPORTED_MARKER


def report_unexpected_error(
    error: BaseException,
    *,
    event: str,
    request_id: str | None = None,
    duration_ms: float | None = None,
    error_code: str | None = None,
    status_code: int | None = None,
) -> None:
    """Emit at most one sanitized diagnostic for an exception instance.

    Args:
        error: Exact exception whose traceback should be recorded.
        event: Stable event name identifying the reporting boundary.
        request_id: Optional trusted request identifier for correlation.
        duration_ms: Optional elapsed execution time in milliseconds.
        error_code: Optional reviewed semantic failure code.
        status_code: HTTP status already started, if any; not proof that
            the response completed successfully.
    """
    if is_error_reported(error):
        return

    # Mark before logging so another boundary cannot report the same instance
    # while this diagnostic is being processed.
    setattr(error, _REPORTED_ATTRIBUTE, _REPORTED_MARKER)

    context: dict[str, object] = {}

    if request_id is not None:
        context["request_id"] = request_id

    if duration_ms is not None:
        context["duration_ms"] = duration_ms

    if error_code is not None:
        context["error_code"] = error_code

    if status_code is not None:
        context["status_code"] = status_code

    logger.error(event, exc_info=error, **context)
