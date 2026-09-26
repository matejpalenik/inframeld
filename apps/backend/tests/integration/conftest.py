"""Provide isolated PostgreSQL databases for backend integration tests."""

from collections.abc import AsyncGenerator, Generator

import pytest
import pytest_asyncio
from tests.support.postgres import temporary_database

from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.shared.infrastructure.migrations.migration_runner import run_migrations
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings


@pytest.fixture
def temporary_postgres_settings() -> Generator[DatabaseSettings]:
    """Provide settings for a newly created database and remove it after the test."""
    with temporary_database(get_settings().database) as settings:
        yield settings


@pytest_asyncio.fixture
async def database(temporary_postgres_settings: DatabaseSettings) -> AsyncGenerator[Database]:
    """Start the application database against a fresh, migrated test database."""
    run_migrations(temporary_postgres_settings)
    database = Database(temporary_postgres_settings)
    await database.startup()

    try:
        yield database
    finally:
        await database.shutdown()
