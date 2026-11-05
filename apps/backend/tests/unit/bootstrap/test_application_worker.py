import asyncio
from collections.abc import Callable, Coroutine
from typing import override

import pytest
from pydantic import SecretStr
from structlog.testing import capture_logs

from inframeld_backend.bootstrap import application_worker
from inframeld_backend.bootstrap.application_worker import main, run_application_worker
from inframeld_backend.bootstrap.application_worker_application_settings import (
    ApplicationWorkerApplicationSettings,
)
from inframeld_backend.bootstrap.application_worker_operations import ApplicationWorkerOperations
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.protocols.artifact_cleanup_preparer import (
    ArtifactCleanupPreparer,
)
from inframeld_backend.shared.application.protocols.artifact_store import ArtifactStore
from inframeld_backend.shared.application.protocols.job_checkpoints import JobCheckpoints
from inframeld_backend.shared.application.protocols.job_effect_observation_recorder import (
    JobEffectObservationRecorder,
)
from inframeld_backend.shared.application.protocols.job_handler import JobHandler
from inframeld_backend.shared.application.services.artifact_cleanup_job_handler import (
    ArtifactCleanupJobHandler,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.settings.job_settings import JobSettings


def test_invalid_configuration_fails_safely_before_any_worker_resources(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for key in ("HOST", "NAME", "USER", "PASSWORD"):
        monkeypatch.delenv("INFRAMELD_DATABASE__" + key, raising=False)
    assert main() == 2
    assert capsys.readouterr().out == '{"code":"invalid_configuration"}\n'


class MockStartupDatabase(Database):
    """Control a blocked startup while retaining real lazy pool disposal."""

    def __init__(self, settings: DatabaseSettings, *, blocked: bool) -> None:
        super().__init__(settings)
        self.blocked = blocked
        self.entered = asyncio.Event()
        self.canceled = False
        self.closed = False
        self.shutdown_calls = 0

    @override
    async def startup(self) -> None:
        self.entered.set()
        if self.blocked:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.canceled = True
                raise

    @override
    async def shutdown(self) -> None:
        self.shutdown_calls += 1
        await super().shutdown()
        self.closed = True


class MockBlockedInstallationIdentityReader(PostgresInstallationIdentityReader):
    def __init__(self, database: Database) -> None:
        super().__init__(database)
        self.entered = asyncio.Event()
        self.canceled = False

    @override
    async def read(self) -> InstallationId:
        self.entered.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.canceled = True
            raise
        raise AssertionError("The blocked identity read cannot complete independently.")


def _startup_resources(
    monkeypatch: pytest.MonkeyPatch,
    *,
    block_database: bool = False,
    database_timeout_seconds: float = 0.01,
) -> tuple[
    ApplicationWorkerApplicationSettings, MockStartupDatabase, MockBlockedInstallationIdentityReader
]:
    settings = ApplicationWorkerApplicationSettings(
        database=DatabaseSettings(name="test", user="test", password=SecretStr("test")),
        artifact_storage=ArtifactStorageSettings(
            endpoint_url="https://storage.example.test",
            bucket="private-artifacts",
            access_key_id=SecretStr("unit-access"),
            secret_access_key=SecretStr("unit-secret"),
        ),
        jobs=JobSettings(
            lease_seconds=3,
            database_timeout_seconds=database_timeout_seconds,
            shutdown_seconds=0.01,
        ),
    )
    database = MockStartupDatabase(settings.database, blocked=block_database)
    reader = MockBlockedInstallationIdentityReader(database)

    def database_factory(settings: DatabaseSettings) -> Database:
        return database

    def identity_reader_factory(database: Database) -> PostgresInstallationIdentityReader:
        return reader

    monkeypatch.setattr(application_worker, "Database", database_factory)
    monkeypatch.setattr(
        application_worker, "PostgresInstallationIdentityReader", identity_reader_factory
    )
    return settings, database, reader


async def _cancel_worker(worker: asyncio.Task[None]) -> None:
    if not worker.done():
        worker.cancel()
    await asyncio.gather(worker, return_exceptions=True)


@pytest.mark.asyncio
async def test_startup_identity_timeout_closes_pool_without_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, database, reader = _startup_resources(monkeypatch)
    stopped = asyncio.Event()
    with capture_logs() as logs:
        worker = asyncio.create_task(
            run_application_worker(
                settings,
                stopped,
                (),
                database=database,
                operations=ApplicationWorkerOperations(database, settings.jobs, stopped),
            )
        )
        try:
            await asyncio.wait_for(reader.entered.wait(), timeout=1)
            done, _ = await asyncio.wait((worker,), timeout=0.25)
            assert worker in done, "Startup identity read exceeded its database operation budget."
            with pytest.raises(TimeoutError):
                await worker
            assert reader.canceled and database.closed
            assert all(entry["event"] != "application_worker_ready" for entry in logs)
        finally:
            await _cancel_worker(worker)


@pytest.mark.asyncio
async def test_stop_during_startup_identity_read_closes_pool_without_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, database, reader = _startup_resources(monkeypatch, database_timeout_seconds=1)
    stopped = asyncio.Event()
    with capture_logs() as logs:
        worker = asyncio.create_task(
            run_application_worker(
                settings,
                stopped,
                (),
                database=database,
                operations=ApplicationWorkerOperations(database, settings.jobs, stopped),
            )
        )
        try:
            await asyncio.wait_for(reader.entered.wait(), timeout=1)
            stopped.set()
            done, _ = await asyncio.wait((worker,), timeout=0.25)
            assert worker in done, "A stop request must interrupt startup identity access."
            await worker
            assert reader.canceled and database.closed
            assert all(entry["event"] != "application_worker_ready" for entry in logs)
        finally:
            await _cancel_worker(worker)


@pytest.mark.asyncio
async def test_stop_during_database_startup_closes_pool_without_readiness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, database, reader = _startup_resources(monkeypatch, block_database=True)
    stopped = asyncio.Event()
    with capture_logs() as logs:
        worker = asyncio.create_task(
            run_application_worker(
                settings,
                stopped,
                (),
                database=database,
                operations=ApplicationWorkerOperations(database, settings.jobs, stopped),
            )
        )
        try:
            await asyncio.wait_for(database.entered.wait(), timeout=1)
            stopped.set()
            done, _ = await asyncio.wait((worker,), timeout=0.25)
            assert worker in done, "A stop request must interrupt database startup."
            await worker
            assert database.canceled and database.closed
            assert not reader.entered.is_set()
            assert all(entry["event"] != "application_worker_ready" for entry in logs)
        finally:
            await _cancel_worker(worker)


class MockInvalidHandler(JobHandler):
    @override
    def payload_type(self) -> tuple[str, int]:
        return "invalid kind", 1

    @override
    async def run(self, context: JobAttemptContextDTO, checkpoints: JobCheckpoints) -> None:
        raise AssertionError("Invalid handlers cannot execute work.")


class MockClosingStorage(S3ArtifactStore):
    def __init__(self) -> None:
        self.closed = False
        self.close_calls = 0

    @override
    async def close(self) -> None:
        self.close_calls += 1
        self.closed = True


@pytest.mark.asyncio
async def test_handler_validation_failure_closes_pool_before_any_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, database, _ = _startup_resources(monkeypatch)
    stopped = asyncio.Event()
    try:
        with pytest.raises(ValueError):
            await run_application_worker(
                settings,
                stopped,
                (MockInvalidHandler(),),
                database=database,
                operations=ApplicationWorkerOperations(database, settings.jobs, stopped),
            )
        assert database.closed and database.shutdown_calls == 1
        assert not database.entered.is_set()
    finally:
        if not database.closed:
            await database.shutdown()


@pytest.mark.asyncio
async def test_preloop_failure_closes_constructed_storage_and_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings, database, _ = _startup_resources(monkeypatch)
    storage = MockClosingStorage()
    failure = RuntimeError("Cleanup handler construction failed.")

    def storage_factory(
        settings: ArtifactStorageSettings,
        *,
        observations: JobEffectObservationRecorder | None = None,
    ) -> S3ArtifactStore:
        return storage

    def failing_handler(
        preparer: ArtifactCleanupPreparer, artifacts: ArtifactStore
    ) -> ArtifactCleanupJobHandler:
        raise failure

    async def unexpected_runtime(
        settings: ApplicationWorkerApplicationSettings,
        stopped: asyncio.Event,
        handlers: tuple[JobHandler, ...],
        *,
        database: Database,
        operations: ApplicationWorkerOperations,
    ) -> None:
        raise AssertionError("Runtime entered without valid handler construction.")

    def add_handler(signum: int, callback: Callable[[], None]) -> None:
        pass

    def remove_handler(signum: int) -> bool:
        return True

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "add_signal_handler", add_handler)
    monkeypatch.setattr(loop, "remove_signal_handler", remove_handler)
    monkeypatch.setattr(application_worker, "S3ArtifactStore", storage_factory)
    monkeypatch.setattr(application_worker, "ArtifactCleanupJobHandler", failing_handler)
    monkeypatch.setattr(application_worker, "run_application_worker", unexpected_runtime)
    pending: Coroutine[None, None, None] | None = None

    def capture_runtime(coroutine: Coroutine[None, None, None]) -> None:
        nonlocal pending
        pending = coroutine

    def configured_settings(value: object) -> ApplicationWorkerApplicationSettings:
        return settings

    monkeypatch.setattr(asyncio, "run", capture_runtime)
    monkeypatch.setattr(ApplicationWorkerApplicationSettings, "model_validate", configured_settings)
    try:
        assert main() == 0 and pending is not None
        with pytest.raises(RuntimeError) as caught:
            await pending
        assert caught.value is failure
        assert storage.closed and storage.close_calls == 1
        assert database.closed and database.shutdown_calls == 1
        assert not database.entered.is_set()
    finally:
        if not storage.closed:
            await storage.close()
        if not database.closed:
            await database.shutdown()
