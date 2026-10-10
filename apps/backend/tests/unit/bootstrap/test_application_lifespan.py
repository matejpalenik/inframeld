"""Verify resource cleanup during successful serving and failed startup."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import override

import pytest
from ory_hydra_client.api_client import ApiClient as HydraApiClient
from ory_kratos_client.api_client import ApiClient as KratosApiClient
from pydantic import SecretStr

from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings


class RecordingDatabase(Database):
    """Use real database disposal with deterministic startup outcomes and no network."""

    def __init__(self, fail_startup: bool = False, fail_shutdown: bool = False) -> None:
        """Create unconnected engine resources and choose the startup outcome."""
        super().__init__(DatabaseSettings(name="test", user="test", password=SecretStr("test")))
        self.fail_startup = fail_startup
        self.fail_shutdown = fail_shutdown
        self.started = False
        self.closed = False

    @override
    async def startup(self) -> None:
        """Simulate successful initialization or a partially completed startup."""
        self.started = True
        if self.fail_startup:
            raise RuntimeError("startup failed")

    @override
    async def shutdown(self) -> None:
        """Dispose the actual engine and record resource release."""
        await super().shutdown()
        self.closed = True
        if self.fail_shutdown:
            raise RuntimeError("shutdown failed")


@contextmanager
def _owned_resources(database: Database) -> Generator[ApplicationResources]:
    """Allocate real SDK pools without network calls - clean up even a failing test."""
    public_client = KratosApiClient()
    admin_client = KratosApiClient()
    hydra_client = HydraApiClient()
    clients = (public_client, admin_client, hydra_client)

    try:
        for client in clients:
            pool = client.rest_client.pool_manager
            pool.connection_from_url("http://example.test")
            assert len(pool.pools) == 1

        yield ApplicationResources(
            database=database,
            kratos_client=public_client,
            kratos_admin_client=admin_client,
            hydra_client=hydra_client,
        )
    finally:
        for client in clients:
            client.rest_client.pool_manager.clear()


def _assert_provider_pools_empty(resources: ApplicationResources) -> None:
    for client in (resources.kratos_client, resources.kratos_admin_client, resources.hydra_client):
        assert client is not None
        assert len(client.rest_client.pool_manager.pools) == 0


@pytest.mark.asyncio
async def test_lifespan_releases_database_and_all_provider_pools() -> None:
    """Close PostgreSQL and all three provider pools after normal serving."""
    database = RecordingDatabase()

    with _owned_resources(database) as resources:
        async with application_lifespan(resources):
            assert database.started
            assert not database.closed

        assert database.closed
        _assert_provider_pools_empty(resources)


@pytest.mark.asyncio
async def test_failed_startup_also_releases_all_provider_pools() -> None:
    """If startup fails, admit no requests and release already-created resources."""
    database = RecordingDatabase(fail_startup=True)

    with _owned_resources(database) as resources:
        with pytest.raises(RuntimeError, match="startup failed"):
            async with application_lifespan(resources):
                pytest.fail("Failed startup must never admit requests")

        assert database.closed
        _assert_provider_pools_empty(resources)


@pytest.mark.asyncio
async def test_failed_database_shutdown_still_releases_all_provider_pools() -> None:
    """A database cleanup error must not prevent provider pools from being closed."""
    database = RecordingDatabase(fail_shutdown=True)

    with _owned_resources(database) as resources:
        with pytest.raises(RuntimeError, match="shutdown failed"):
            async with application_lifespan(resources):
                assert database.started

        assert database.closed
        _assert_provider_pools_empty(resources)
