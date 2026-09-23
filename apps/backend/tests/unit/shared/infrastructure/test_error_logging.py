"""Verify that final rendered exception diagnostics never expose secrets."""

import logging

import pytest
import structlog
from sqlalchemy.exc import DBAPIError

from inframeld_backend.shared.infrastructure.logging import configure_logging
from inframeld_backend.shared.infrastructure.settings import LogFormat

LOCAL_SECRET = "synthetic-local-secret"
CAUSE_SECRET = "synthetic-cause-secret"
NOTE_SECRET = "synthetic-note-secret"
GROUP_SECRET = "synthetic-group-secret"
MEMBER_SECRET = "synthetic-member-secret"


class _RecordCaptureHandler(logging.Handler):
    """Capture records after the configured application handler processes them."""

    def __init__(self) -> None:
        """Initialize an empty record collection."""
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        """Retain a processed record for assertions."""
        self.records.append(record)


def _large_exception_group() -> ExceptionGroup[Exception]:
    """Build a group wider and deeper than the diagnostic safety limits."""
    nested: Exception = RuntimeError("leaf")

    for _ in range(10):
        children: list[Exception] = [nested]
        nested = ExceptionGroup("nested", children)

    siblings: list[Exception] = [nested]
    siblings.extend(RuntimeError("sibling") for _ in range(30))

    return ExceptionGroup("root", siblings)


def _raise_nested_failure() -> None:
    """Raise a representative nested failure containing synthetic secrets."""
    local_secret = LOCAL_SECRET

    if not local_secret:
        raise AssertionError("The synthetic local must be populated.")

    try:
        cause = ValueError(CAUSE_SECRET)
        cause.add_note(NOTE_SECRET)
        raise cause
    except ValueError as cause:
        raise ExceptionGroup(
            GROUP_SECRET,
            [RuntimeError(MEMBER_SECRET)],
        ) from cause


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_exception_diagnostic_excludes_sensitive_data(
    log_format: LogFormat,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Retain useful stack identity without rendering sensitive values."""
    configure_logging(level="ERROR", log_format=log_format)
    logger = structlog.get_logger("test.error_logging")

    try:
        _raise_nested_failure()
    except ExceptionGroup:
        logger.exception("synthetic_failure")

    rendered = capsys.readouterr().out

    # Keep enough structural information for developers to locate the failure.
    assert "synthetic_failure" in rendered
    assert "_raise_nested_failure" in rendered
    assert "ValueError" in rendered
    assert "RuntimeError" in rendered
    assert "ExceptionGroup" in rendered

    # Never render values from locals, messages, notes, causes, or group members.
    for secret in (
        LOCAL_SECRET,
        CAUSE_SECRET,
        NOTE_SECRET,
        GROUP_SECRET,
        MEMBER_SECRET,
    ):
        assert secret not in rendered


def test_exception_diagnostic_has_bounded_size(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Bound exception depth, group breadth, and total rendered nodes."""
    configure_logging(level="ERROR", log_format="json")
    logger = structlog.get_logger("test.error_logging")

    logger.error(
        "bounded_failure",
        exc_info=_large_exception_group(),
    )

    rendered = capsys.readouterr().out
    rendered_exception_count = rendered.count("RuntimeError") + rendered.count("ExceptionGroup")

    assert "bounded_failure" in rendered
    assert rendered_exception_count <= 16
    assert "truncated" in rendered


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_standard_library_exception_is_sanitized_and_cleared(
    log_format: LogFormat,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Sanitize stdlib diagnostics and remove raw exception information."""
    configure_logging(level="ERROR", log_format=log_format)

    root_logger = logging.getLogger()
    capture_handler = _RecordCaptureHandler()
    root_logger.addHandler(capture_handler)

    try:
        try:
            _raise_nested_failure()
        except ExceptionGroup:
            logging.getLogger("test.error_logging.stdlib").exception("stdlib_failure")
    finally:
        root_logger.removeHandler(capture_handler)

    rendered = capsys.readouterr().out

    assert "stdlib_failure" in rendered
    assert "_raise_nested_failure" in rendered
    assert "ValueError" in rendered
    assert "RuntimeError" in rendered
    assert "ExceptionGroup" in rendered

    for secret in (
        LOCAL_SECRET,
        CAUSE_SECRET,
        NOTE_SECRET,
        GROUP_SECRET,
        MEMBER_SECRET,
    ):
        assert secret not in rendered

    assert len(capture_handler.records) == 1

    record = capture_handler.records[0]

    assert record.exc_info is None
    assert record.exc_text is None


@pytest.mark.parametrize("log_format", ["json", "console"])
def test_sql_driver_text_is_excluded_from_diagnostic(
    log_format: LogFormat,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Hide both bound values and unsafe driver text in rendered logs."""
    configure_logging(level="ERROR", log_format=log_format)

    private_parameter = "synthetic-private-sql-parameter"
    private_driver_text = "synthetic-private-driver-text"
    error = DBAPIError(
        statement="SELECT :private_value",
        params={"private_value": private_parameter},
        orig=RuntimeError(private_driver_text),
        hide_parameters=True,
    )

    # Parameter hiding does not sanitize the driver's own message.
    assert private_parameter not in str(error)
    assert private_driver_text in str(error)

    structlog.get_logger("test.error_logging").error(
        "database_failure",
        exc_info=error,
    )

    rendered = capsys.readouterr().out
    assert "database_failure" in rendered
    assert "DBAPIError" in rendered
    assert private_parameter not in rendered
    assert private_driver_text not in rendered
