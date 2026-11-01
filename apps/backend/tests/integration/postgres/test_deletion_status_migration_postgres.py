"""Qualify retained status storage through the real operator migration chain."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.deletion_status_scenarios import MockDeletionStatusScenarios
from tests.support.postgres import database_connection

from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.parametrize("table_name", ["deletion_status_bindings", "deletion_status_observations"])
def test_migration_installs_retained_status_storage(
    temporary_postgres_settings: DatabaseSettings, table_name: str
) -> None:
    """Install both retained records rather than relying on a test-only schema."""
    run_migrations(temporary_postgres_settings)

    with database_connection(temporary_postgres_settings) as connection:
        assert inspect(connection).has_table(table_name, schema="public"), table_name


@pytest.mark.asyncio
async def test_upgrade_downgrade_and_reupgrade_preserve_original_foundation(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Install only retained storage above current main without replacing request or identity data."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    config.attributes["database_settings"] = temporary_postgres_settings
    command.upgrade(config, "0010_durable_jobs")
    database = Database(temporary_postgres_settings)

    try:
        async with database.session() as session, session.begin():
            seed = await MockDeletionStatusScenarios.seed_native_request(session)

        for revision in (
            "0013_deletion_status",
            "0010_durable_jobs",
            "0013_deletion_status",
        ):
            if revision == "0010_durable_jobs":
                command.downgrade(config, revision)
            else:
                run_migrations(temporary_postgres_settings)

            with database_connection(temporary_postgres_settings) as connection:
                assert connection.scalar(select(AlembicVersionRow.version_num)) == revision
                for table in ("deletion_status_bindings", "deletion_status_observations"):
                    assert inspect(connection).has_table(table, schema="public") is (
                        revision == "0013_deletion_status"
                    )

            async with database.session() as session:
                original = await session.get(
                    IdempotencyReservationRow, seed.reservation.operation_id.value
                )
                assert original is not None
                assert original.principal_id == seed.request.principal_id.value
                assert original.request_key == seed.request.key.value
                assert original.request_fingerprint == seed.request.fingerprint
                assert await session.scalar(select(InstallationIdentityRow.installation_id)) == (
                    seed.installation_id.value
                )
    finally:
        await database.shutdown()


@pytest.mark.asyncio
@pytest.mark.parametrize("days", [0, -1, 91])
async def test_schema_rejects_nonpositive_or_excessive_retention_without_changing_capture(
    database: Database, days: int
) -> None:
    async with database.session() as session, session.begin():
        await MockDeletionStatusScenarios.seed_private_binding(session)
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(update(DeletionStatusBindingRow).values(retention_days=days))
        async with session.begin():
            assert await session.scalar(select(DeletionStatusBindingRow.retention_days)) == 30
