"""Provide isolated PostgreSQL databases for backend integration tests."""

from collections.abc import AsyncGenerator, Generator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
import pytest_asyncio
from psycopg import sql

from inframeld_backend.shared.infrastructure.database import Database
from inframeld_backend.shared.infrastructure.migrations import run_migrations
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings, get_settings


def _connect(
    settings: DatabaseSettings,
    *,
    database_name: str | None = None,
    autocommit: bool = False,
) -> psycopg.Connection[Any]:
    """Connect to the configured PostgreSQL server or one of its databases."""
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.name if database_name is None else database_name,
        user=settings.user,
        password=settings.password.get_secret_value(),
        autocommit=autocommit,
    )


@pytest.fixture
def temporary_postgres_settings() -> Generator[DatabaseSettings]:
    """Create and later remove an isolated database for one integration test."""
    base_settings = get_settings().database
    database_name = f"inframeld_test_{uuid4().hex}"

    with (
        _connect(base_settings, database_name="postgres", autocommit=True) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    try:
        yield base_settings.model_copy(update={"name": database_name})
    finally:
        with (
            _connect(base_settings, database_name="postgres", autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(database_name))
            )


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
