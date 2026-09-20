import logging
import sys

import structlog
from structlog.typing import Processor

from inframeld_backend.shared.infrastructure.settings import LogFormat, LogLevel


def _logging_level(level: LogLevel) -> int:
    return logging.getLevelNamesMapping()[level]


def configure_logging(*, level: LogLevel, log_format: LogFormat) -> None:
    """Configure Structlog and standard-library logging for the application."""
    timestamper = structlog.processors.TimeStamper(fmt="iso", utc=True)

    exception_processor: Processor = (
        structlog.processors.dict_tracebacks
        if log_format == "json"
        else structlog.processors.format_exc_info
    )

    shared_processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        timestamper,
        structlog.processors.StackInfoRenderer(),
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

    renderer: Processor = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer()
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(_logging_level(level))

    # Route Uvicorn's standard-library logs through the same formatter
    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(logging.NOTSET)

    # RequestContextMiddleware is the cannonical access logger - disable the Uvicorn default.
    logging.getLogger("uvicorn.access").disabled = True
