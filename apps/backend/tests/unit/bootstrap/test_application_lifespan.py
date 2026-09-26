"""Verify resource cleanup during successful serving and failed startup."""

from typing import override

import pytest
from ory_kratos_client.api_client import ApiClient
from pydantic import SecretStr

from inframeld_backend.bootstrap.application_lifespan import application_lifespan
from inframeld_backend.bootstrap.application_resources import ApplicationResources
from inframeld_backend.shared.infrastructure.postgres.database import Database
from inframeld_backend.shared.infrastructure.postgres.database_settings import DatabaseSettings


class RecordingDatabase(Database):
    """Use real database disposal with deterministic startup outcomes and no network."""

    def __init__(self, fail_startup: bool) -> None:
        """Create unconnected engine resources and choose the startup outcome."""
        super().__init__(DatabaseSettings(name="test", user="test", password=SecretStr("test")))
        self.fail_startup = fail_startup
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


@pytest.mark.asyncio
async def test_lifespan_releases_database_and_kratos_pool() -> None:
    """Release both resource owners after the application finishes serving."""
    database = RecordingDatabase(False)
    client = ApiClient()
    pool = client.rest_client.pool_manager
    pool.connection_from_url("http://example.test")
    assert len(pool.pools) == 1
    async with application_lifespan(ApplicationResources(database, client)):
        assert database.started
        assert not database.closed
    assert database.closed
    assert len(pool.pools) == 0


@pytest.mark.asyncio
async def test_failed_startup_also_releases_kratos_pool() -> None:
    """Release resources created before database initialization fails."""
    database = RecordingDatabase(True)
    client = ApiClient()
    pool = client.rest_client.pool_manager
    pool.connection_from_url("http://example.test")
    with pytest.raises(RuntimeError, match="startup failed"):
        async with application_lifespan(ApplicationResources(database, client)):
            pytest.fail("Failed startup must never admit requests")
    assert database.closed
    assert len(pool.pools) == 0
