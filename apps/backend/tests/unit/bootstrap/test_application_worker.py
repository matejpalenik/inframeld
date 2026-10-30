import asyncio
from typing import override

import pytest
from pydantic import SecretStr
from structlog.testing import capture_logs

from inframeld_backend.bootstrap import application_worker
from inframeld_backend.bootstrap.application_worker import main, run_application_worker
from inframeld_backend.bootstrap.application_worker_application_settings import (
    ApplicationWorkerApplicationSettings,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
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
    with capture_logs() as logs:
        worker = asyncio.create_task(run_application_worker(settings, asyncio.Event()))
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
        worker = asyncio.create_task(run_application_worker(settings, stopped))
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
        worker = asyncio.create_task(run_application_worker(settings, stopped))
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
