"""Register only a trusted test handler, then run the production worker lifecycle."""

import asyncio

from inframeld_backend.bootstrap.application_worker import run_application_worker
from inframeld_backend.bootstrap.application_worker_application_settings import (
    ApplicationWorkerApplicationSettings,
)
from inframeld_backend.shared.infrastructure.logging.logging_configuration import configure_logging
from inframeld_backend.shared.infrastructure.types.log_format import LogFormat
from inframeld_backend.shared.infrastructure.types.log_level import LogLevel
from tests.support.application_job_handler import BoundedJobHandler


async def _run() -> None:
    import signal

    settings = ApplicationWorkerApplicationSettings.model_validate({})
    configure_logging(level=LogLevel.INFO, log_format=LogFormat.JSON)
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.add_signal_handler(signal.SIGTERM, stopped.set)
    try:
        await run_application_worker(settings, stopped, (BoundedJobHandler(),))
    finally:
        loop.remove_signal_handler(signal.SIGTERM)


if __name__ == "__main__":
    asyncio.run(_run())
