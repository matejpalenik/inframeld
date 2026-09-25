import json
import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import Connection, text
from sqlalchemy.exc import SQLAlchemyError

from inframeld_backend.shared.infrastructure import migrations as migration_module
from inframeld_backend.shared.infrastructure.database import (
    Database,
    DatabaseSchemaCompatibilityError,
    DatabaseStartupError,
)
from inframeld_backend.shared.infrastructure.migrations import (
    BACKEND_ROOT,
    MIGRATION_LOCK_KEY,
    SUPPORTED_SCHEMA_REVISION,
    MigrationLockError,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings

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


def test_empty_database_migration_records_supported_revision(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Prove an empty database is initialized at the supported revision."""

    settings = temporary_postgres_settings

    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.alembic_version')")
        assert cursor.fetchone() == (None,)

    run_migrations(settings)

    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM alembic_version")
        version = cursor.fetchone()

    assert version == (SUPPORTED_SCHEMA_REVISION,)


def test_repeating_current_migration_preserves_existing_data(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Prove rerunning the current migration preserves existing data."""

    settings = temporary_postgres_settings

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
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Prove a second migration attempt exits when the migration lock is held."""

    settings = temporary_postgres_settings.model_copy(
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
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Prove startup rejects an empty database without creating schema metadata."""

    database = Database(temporary_postgres_settings)

    try:
        with pytest.raises(DatabaseSchemaCompatibilityError, match="schema is not initialized"):
            await database.startup()
    finally:
        await database.shutdown()

    with _connect(temporary_postgres_settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass('public.alembic_version')")
        assert cursor.fetchone() == (None,)


@pytest.mark.asyncio
async def test_startup_accepts_supported_schema_revision(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Prove startup accepts the exact schema revision supported by the application."""

    run_migrations(temporary_postgres_settings)

    database = Database(temporary_postgres_settings)

    try:
        await database.startup()
    finally:
        await database.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("unsupported_revision", ["0000_legacy", "9999_future"])
async def test_startup_rejects_unsupported_schema_revision(
    temporary_postgres_settings: DatabaseSettings, unsupported_revision: str
) -> None:
    """Prove startup rejects schema revisions outside the supported compatibility window."""

    run_migrations(temporary_postgres_settings)

    with _connect(temporary_postgres_settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            "UPDATE public.alembic_version SET version_num = %s", (unsupported_revision,)
        )

    database = Database(temporary_postgres_settings)

    try:
        with pytest.raises(DatabaseStartupError, match="Unsupported PostgreSQL schema revision"):
            await database.startup()
    finally:
        await database.shutdown()


def test_failed_migration_does_not_record_success(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Prove a failed migration does not leave a successful revision recorded."""

    # Create a deliberately invalid version table in the temporary database.
    # Alembic's attempt to insert the revision will fail.

    with _connect(temporary_postgres_settings) as connection, connection.cursor() as cursor:
        cursor.execute(
            """CREATE TABLE public.alembic_version ( version_num VARCHAR(32) NOT NULL CHECK (false) )"""
        )

    with pytest.raises(SQLAlchemyError):
        run_migrations(temporary_postgres_settings)

    with _connect(temporary_postgres_settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT version_num FROM public.alembic_version")
        assert cursor.fetchall() == []


def test_failed_migration_hides_bound_parameters(
    temporary_postgres_settings: DatabaseSettings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Check the Alembic engine hides an actual bound value on failure."""
    private_value = "synthetic-private-migration-value"
    missing_table = f"missing_{uuid4().hex}"

    @contextmanager
    def failing_lock(
        connection: Connection,
        _timeout_seconds: float,
    ) -> Generator[None]:
        connection.execute(
            text(f'SELECT :private_value FROM "{missing_table}"'),
            {"private_value": private_value},
        )
        yield

    # Alembic imports this hook while loading env.py. The query runs through
    # Alembic's real engine, but fails before any migration is applied.
    monkeypatch.setattr(migration_module, "migration_lock", failing_lock)

    with pytest.raises(SQLAlchemyError) as failure:
        run_migrations(temporary_postgres_settings)

    rendered = str(failure.value)
    assert private_value not in rendered
    assert "[SQL parameters hidden due to hide_parameters=True]" in rendered


def test_migration_cli_does_not_disclose_driver_message(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Keep a driver-supplied message out of operator-visible output."""
    private_value = "synthetic-private-migration-driver-message"
    settings = temporary_postgres_settings

    with _connect(settings) as connection, connection.cursor() as cursor:
        cursor.execute("CREATE TABLE public.alembic_version (version_num VARCHAR(32) NOT NULL)")
        cursor.execute(
            """
            CREATE FUNCTION public.fail_migration_version() RETURNS trigger
            LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'synthetic-private-migration-driver-message';
            END;
            $$
            """
        )
        cursor.execute(
            """
            CREATE TRIGGER fail_migration_version
            BEFORE INSERT ON public.alembic_version
            FOR EACH ROW EXECUTE FUNCTION public.fail_migration_version()
            """
        )

    environment = os.environ.copy()
    environment["INFRAMELD_DATABASE__NAME"] = settings.name
    environment["INFRAMELD_LOG_FORMAT"] = "json"

    result = subprocess.run(
        [sys.executable, "-m", "inframeld_backend.migrate"],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode != 0
    assert private_value not in result.stdout + result.stderr

    diagnostic = json.loads(result.stdout.strip().splitlines()[-1])
    assert diagnostic["event"] == "migration_failed"
    assert "exception" in diagnostic
