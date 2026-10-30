import asyncio
import signal
from contextlib import suppress
from datetime import UTC, datetime
from uuid import UUID, uuid4

import structlog
from pydantic import ValidationError
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.bootstrap.application_worker_application_settings import (
    ApplicationWorkerApplicationSettings,
)
from inframeld_backend.bootstrap.application_worker_operations import ApplicationWorkerOperations
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
    JobWorkerStoppingError,
    SafeJobRetryError,
)
from inframeld_backend.shared.application.protocols.job_handler import JobHandler
from inframeld_backend.shared.application.services.job_execution_service import JobExecutionService
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.infrastructure.logging.logging_configuration import configure_logging
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.readers.postgres_job_queue_status_reader import (
    PostgresJobQueueStatusReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_job_store import PostgresJobStore
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)


async def _wait(stopped: asyncio.Event, seconds: float) -> None:
    with suppress(TimeoutError):
        await asyncio.wait_for(stopped.wait(), timeout=seconds)


async def _claim(
    database: Database,
    settings: ApplicationWorkerApplicationSettings,
    worker_id: UUID,
    supported: tuple[tuple[str, int], ...],
) -> JobAttemptContextDTO | None:
    try:
        async with (
            asyncio.timeout(settings.jobs.database_timeout_seconds),
            database.session() as session,
        ):
            return await JobExecutionService(
                SqlAlchemyTransactionManager(session),
                PostgresJobStore(session),
                supported_payloads=supported,
                worker_id=worker_id,
                lease_seconds=settings.jobs.lease_seconds,
                work_seconds=settings.jobs.work_seconds,
            ).claim_next()
    except (TimeoutError, OperationalError, InterfaceError, SqlAlchemyTimeoutError):
        raise DependencyUnavailableError("The ordinary job claim could not be confirmed.") from None


async def _execute(
    context: JobAttemptContextDTO,
    handler: JobHandler,
    operations: ApplicationWorkerOperations,
    lease_seconds: float,
) -> None:
    log = structlog.get_logger()
    work: asyncio.Task[None] | None = None
    renew: asyncio.Task[None] | None = None

    async def keep_lease() -> None:
        while True:
            await asyncio.sleep(lease_seconds / 3)
            await operations.renew(context)

    try:
        await operations.check(context)
        work = asyncio.create_task(handler.run(context, operations))
        renew = asyncio.create_task(keep_lease())
        remaining = max(0.0, (context.work_deadline - datetime.now(UTC)).total_seconds())
        async with asyncio.timeout(remaining):
            done, _ = await asyncio.wait((work, renew), return_when=asyncio.FIRST_COMPLETED)
            if renew in done:
                await renew
                raise RuntimeError("The job renewal loop ended unexpectedly.")
            await work
            await operations.succeed(context)
        log.info(
            "application_job_finished",
            job_id=str(context.job_id.value),
            operation_id=context.operation_id.value,
        )
    except (JobStoppedError, JobFenceLostError, JobWorkerStoppingError):
        log.info(
            "application_job_stopped",
            job_id=str(context.job_id.value),
            category="current_work_stopped",
        )
    except (DependencyUnavailableError, TimeoutError, SafeJobRetryError):
        # A missing acknowledgment is not proof that the prior effect did not happen.
        log.warning(
            "application_job_deferred",
            job_id=str(context.job_id.value),
            category="bounded_attempt_recovery",
        )
    except Exception:
        with suppress(ConflictError, DependencyUnavailableError, JobStoppedError):
            await operations.fail(context)
        log.error(
            "application_job_failed", job_id=str(context.job_id.value), category="handler_failed"
        )
    finally:
        for task in (work, renew):
            if task is not None and not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (work, renew) if task is not None), return_exceptions=True
        )


async def run_application_worker(
    settings: ApplicationWorkerApplicationSettings,
    stopped: asyncio.Event,
    handlers: tuple[JobHandler, ...] = (),
) -> None:
    """Run one fenced ordinary attempt, preserving accepted work on bounded shutdown."""
    supported = tuple(handler.payload_type() for handler in handlers)
    for kind, version in supported:
        JobPayload(kind, version, b"")
    if len(set(supported)) != len(supported):
        raise ValueError("A job payload must have one trusted handler registration.")
    database = Database(settings.database)
    operations = ApplicationWorkerOperations(database, settings.jobs, stopped)
    worker_id = uuid4()
    log = structlog.get_logger()
    startup: asyncio.Task[None] | None = None
    work: asyncio.Task[None] | None = None
    stop_wait: asyncio.Task[bool] | None = None

    async def initialize() -> None:
        await database.startup()
        async with asyncio.timeout(settings.jobs.database_timeout_seconds):
            await PostgresInstallationIdentityReader(database).read()

    async def loop() -> None:
        if stopped.is_set():
            return
        log.info("application_worker_ready", worker_id=str(worker_id))
        last_report = 0.0
        while not stopped.is_set():
            try:
                context = await _claim(database, settings, worker_id, supported)
                now = asyncio.get_running_loop().time()
                if now - last_report >= 30:
                    async with (
                        asyncio.timeout(settings.jobs.database_timeout_seconds),
                        database.session() as session,
                    ):
                        status = await PostgresJobQueueStatusReader(session).read()
                    log.info(
                        "application_worker_queue",
                        queue_depth=status.depth,
                        oldest_eligible_age_seconds=status.oldest_eligible_age_seconds,
                        active=status.active,
                    )
                    last_report = now
                if context is None:
                    await _wait(stopped, settings.jobs.poll_seconds)
                else:
                    handler = next(
                        handler
                        for handler in handlers
                        if handler.payload_type() == (context.payload.kind, context.payload.version)
                    )
                    await _execute(context, handler, operations, settings.jobs.lease_seconds)
            except (
                ConflictError,
                DependencyUnavailableError,
                TimeoutError,
                OperationalError,
                InterfaceError,
                SqlAlchemyTimeoutError,
            ):
                log.warning("application_worker_deferred", category="required_state_unavailable")
                await _wait(stopped, settings.jobs.poll_seconds)

    try:
        if stopped.is_set():
            return
        stop_wait = asyncio.create_task(stopped.wait())
        startup = asyncio.create_task(initialize())
        await asyncio.wait((startup, stop_wait), return_when=asyncio.FIRST_COMPLETED)
        if stopped.is_set():
            return
        await startup

        work = asyncio.create_task(loop())
        await asyncio.wait((work, stop_wait), return_when=asyncio.FIRST_COMPLETED)
        if work.done():
            await work
        else:
            try:
                async with asyncio.timeout(settings.jobs.shutdown_seconds):
                    await asyncio.shield(work)
            except TimeoutError:
                work.cancel()
                await asyncio.gather(work, return_exceptions=True)
    finally:
        tasks = tuple(task for task in (startup, work, stop_wait) if task is not None)
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(
            *(task for task in (startup, work) if task is not None), return_exceptions=True
        )
        if stop_wait is not None:
            await asyncio.gather(stop_wait, return_exceptions=True)
        await database.shutdown()


async def _serve(settings: ApplicationWorkerApplicationSettings) -> None:
    stopped = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(signum, stopped.set)
    try:
        await run_application_worker(settings, stopped)
    finally:
        for signum in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(signum)


def main() -> int:
    try:
        settings = ApplicationWorkerApplicationSettings.model_validate({})
    except ValidationError:
        print('{"code":"invalid_configuration"}')
        return 2
    configure_logging(level=settings.log_level, log_format=settings.log_format)
    try:
        asyncio.run(_serve(settings))
    except KeyboardInterrupt:
        return 0
    except Exception:
        structlog.get_logger().error(
            "application_worker_stopped", category="required_state_unavailable"
        )
        return 1
    return 0
