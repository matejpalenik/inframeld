import os
from collections.abc import Generator
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from psycopg import sql

from inframeld_backend.shared.infrastructure.database import Database, DatabaseStartupError
from inframeld_backend.shared.infrastructure.migrations import (
    MIGRATION_LOCK_KEY,
    SUPPORTED_SCHEMA_REVISION,
    MigrationLockError,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings, get_settings

pytestmark = [
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
    )
]


def _connect(
    settings: DatabaseSettings, *, database_name: str | None = None, autocommit: bool = False
) -> psycopg.Connection[Any]:
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.name if database_name is None else database_name,
        user=settings.user,
        password=settings.password.get_secret_value(),
        autocommit=autocommit,
    )


@pytest.fixture
def migration_database_settings() -> Generator[DatabaseSettings]:
    base_settings = get_settings().database
    database_name = f"inframeld_migration_{uuid4().hex}"

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


def test_empty_database_migration_records_supported_revision(
    migration_database_settings: DatabaseSettings,
) -> None:

    settings = migration_database_settings

    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.alembic_version')")
        assert cursor.fetchone() == (None,)

    run_migrations(settings)

    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()

    assert version == (SUPPORTED_SCHEMA_REVISION,)


def test_repeating_current_migration_preserves_existing_data(
    migration_database_settings: DatabaseSettings,
) -> None:
    settings = migration_database_settings

    run_migrations(settings)

    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TABLE migration_sentinel (value TEXT NOT NULL)")

        cursor.execute(
            "INSERT INTO migration_sentinel (value) VALUES (%s)",
            ("preserve-me",),
        )

    run_migrations(settings)

    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT value FROM migration_sentinel")
        value = cursor.fetchone()

    assert value == ("preserve-me",)


def test_migration_command_refuses_a_contended_lock(
    migration_database_settings: DatabaseSettings,
) -> None:
    settings = migration_database_settings.model_copy(
        update={"migration_lock_timeout_seconds": 0.5}
    )

    with _connect(settings, autocommit=True) as blocker, blocker.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,))

        with pytest.raises(MigrationLockError, match="migration lock"):
            run_migrations(settings)

        cursor.execute("SELECT to_regclass('public.alembic_version')")
        assert cursor.fetchone() == (None,)


@pytest.mark.asyncio
async def test_startup_rejects_an_unmigrated_database(
    migration_database_settings: DatabaseSettings,
) -> None:
    database = Database(migration_database_settings)

    try:
        with pytest.raises(DatabaseStartupError, match="schema"):
            await database.startup()
    finally:
        await database.shutdown()
