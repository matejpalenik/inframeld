"""Verify migration compatibility, locking, atomic failure, and diagnostic redaction."""

import json
import os
import subprocess
import sys
from collections.abc import Generator
from contextlib import contextmanager

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Connection,
    String,
    false,
    func,
    inspect,
    literal,
    select,
    update,
)
from sqlalchemy.exc import SQLAlchemyError
from tests.support.database_rows import MigrationSentinelRow, MissingTestRow
from tests.support.postgres import database_connection, database_session

from inframeld_backend.shared.infrastructure.errors.database_errors import (
    DatabaseSchemaCompatibilityError,
    DatabaseStartupError,
)
from inframeld_backend.shared.infrastructure.errors.migration_errors import MigrationLockError
from inframeld_backend.shared.infrastructure.migrations import migration_runner as migration_module
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    MIGRATION_LOCK_KEY,
    SUPPORTED_SCHEMA_REVISION,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


def _has_version_table(settings: DatabaseSettings) -> bool:
    """Observe whether Alembic has initialized the database's revision table."""
    with database_connection(settings) as connection:
        return inspect(connection).has_table("alembic_version", schema="public")


def _create_rejecting_version_table(settings: DatabaseSettings, constraint_name: str) -> None:
    """Force Alembic's revision insertion to fail through an actual database constraint."""
    with database_connection(settings) as connection, connection.begin():
        Operations(MigrationContext.configure(connection)).create_table(
            "alembic_version",
            Column("version_num", String(32), nullable=False),
            CheckConstraint(false(), name=constraint_name),
            schema="public",
        )


def test_empty_database_migration_records_supported_revision(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Initialize an empty database and record the supported schema revision."""
    settings = temporary_postgres_settings
    assert not _has_version_table(settings)
    run_migrations(settings)
    with database_connection(settings) as connection:
        assert connection.scalars(select(AlembicVersionRow.version_num)).all() == [
            SUPPORTED_SCHEMA_REVISION
        ]


def test_repeating_current_migration_preserves_existing_data(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Preserve committed application data when the current migration runs again."""
    settings = temporary_postgres_settings
    run_migrations(settings)
    with database_connection(settings) as connection, connection.begin():
        Operations(MigrationContext.configure(connection)).create_table(
            "migration_sentinel", Column("value", String, primary_key=True)
        )
    with database_session(settings) as session, session.begin():
        session.add(MigrationSentinelRow(value="preserve-me"))
    run_migrations(settings)
    with database_session(settings) as session:
        assert session.scalar(select(MigrationSentinelRow.value)) == "preserve-me"


def test_migration_command_refuses_a_contended_lock(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Bound migration admission when another connection owns the coordination lock."""
    settings = temporary_postgres_settings.model_copy(
        update={"migration_lock_timeout_seconds": 0.5}
    )
    with database_connection(settings, autocommit=True) as blocker:
        blocker.execute(select(func.pg_advisory_lock(MIGRATION_LOCK_KEY)))
        with pytest.raises(MigrationLockError, match="migration lock"):
            run_migrations(settings)
        assert not inspect(blocker).has_table("alembic_version", schema="public")
        blocker.execute(select(func.pg_advisory_unlock(MIGRATION_LOCK_KEY, type_=Boolean())))


@pytest.mark.asyncio
async def test_startup_rejects_an_unmigrated_database(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Refuse an empty database without silently creating an application schema."""
    database = Database(temporary_postgres_settings)
    try:
        with pytest.raises(DatabaseSchemaCompatibilityError, match="schema is not initialized"):
            await database.startup()
    finally:
        await database.shutdown()
    assert not _has_version_table(temporary_postgres_settings)


@pytest.mark.asyncio
async def test_startup_accepts_supported_schema_revision(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Start successfully after the operator installs the supported migration."""
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
    """Refuse both older and newer unqualified schema revisions."""
    run_migrations(temporary_postgres_settings)
    with database_connection(temporary_postgres_settings) as connection, connection.begin():
        connection.execute(update(AlembicVersionRow).values(version_num=unsupported_revision))
    database = Database(temporary_postgres_settings)
    try:
        with pytest.raises(DatabaseStartupError, match="Unsupported PostgreSQL schema revision"):
            await database.startup()
    finally:
        await database.shutdown()


def test_failed_migration_does_not_record_success(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Keep a failed migration from recording a successful revision."""
    settings = temporary_postgres_settings
    _create_rejecting_version_table(settings, "reject_revision")
    with pytest.raises(SQLAlchemyError):
        run_migrations(settings)
    with database_connection(settings) as connection:
        assert connection.scalars(select(AlembicVersionRow.version_num)).all() == []


def test_failed_migration_hides_bound_parameters(
    temporary_postgres_settings: DatabaseSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep an actual bound secret out of Alembic engine failures."""
    private_value = "synthetic-private-migration-value"

    @contextmanager
    def failing_lock(connection: Connection, _timeout_seconds: float) -> Generator[None]:
        """Fail a real statement using Alembic's engine before schema changes begin."""
        connection.execute(select(literal(private_value)).select_from(MissingTestRow))
        yield

    monkeypatch.setattr(migration_module, "migration_lock", failing_lock)
    with pytest.raises(SQLAlchemyError) as failure:
        run_migrations(temporary_postgres_settings)
    assert private_value not in str(failure.value)
    assert "[SQL parameters hidden due to hide_parameters=True]" in str(failure.value)


def test_migration_cli_does_not_disclose_driver_message(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Remove a real driver-supplied constraint marker from operator diagnostics."""
    marker = "synthetic_private_migration_driver_message"
    settings = temporary_postgres_settings
    _create_rejecting_version_table(settings, marker)
    with pytest.raises(SQLAlchemyError) as failure:
        run_migrations(settings)
    assert marker in str(failure.value)
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
    assert marker not in result.stdout + result.stderr
    diagnostic = json.loads(result.stdout.strip().splitlines()[-1])
    assert diagnostic["event"] == "migration_failed"
    assert "exception" in diagnostic
