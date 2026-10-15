"""Verify persistent installation identity without host-state or provider dependencies."""

import asyncio
import os
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError
from tests.support.postgres import temporary_database

from inframeld_backend.shared.infrastructure.errors.installation_identity_error import (
    InstallationIdentityError,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import run_migrations
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_migration_initializes_one_stable_installation_identity(
    database: Database,
) -> None:
    """Ensure setup saves one installation ID that repeated reads keep returning."""
    reader = PostgresInstallationIdentityReader(database)

    first = await reader.read()
    repeated = await reader.read()

    async with database.session() as session:
        stored_ids = (await session.scalars(select(InstallationIdentityRow.installation_id))).all()

    assert repeated == first
    assert stored_ids == [first.value]


@pytest.mark.asyncio
async def test_installation_identity_survives_database_pool_restart(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Keep the same installation ID after closing and reopening database connections."""
    await asyncio.to_thread(run_migrations, temporary_postgres_settings)
    original = Database(temporary_postgres_settings)
    try:
        await original.startup()
        first = await PostgresInstallationIdentityReader(original).read()
    finally:
        await original.shutdown()

    restarted = Database(temporary_postgres_settings)
    try:
        await restarted.startup()
        assert await PostgresInstallationIdentityReader(restarted).read() == first
    finally:
        await restarted.shutdown()


@pytest.mark.asyncio
async def test_repeating_migrations_preserves_installation_identity(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Ensure rerunning migrations cannot replace an existing installation's ID."""
    reader = PostgresInstallationIdentityReader(database)
    original = await reader.read()

    await asyncio.to_thread(run_migrations, temporary_postgres_settings)

    assert await reader.read() == original


@pytest.mark.asyncio
async def test_missing_installation_identity_is_not_regenerated(
    database: Database,
) -> None:
    """Fail when the stored ID is missing instead of silently creating a new identity."""
    async with database.session() as session, session.begin():
        await session.execute(delete(InstallationIdentityRow))

    with pytest.raises(InstallationIdentityError, match="installation identity is missing"):
        await PostgresInstallationIdentityReader(database).read()

    async with database.session() as session:
        assert await session.scalar(select(InstallationIdentityRow.installation_id)) is None


@pytest.mark.asyncio
async def test_new_installation_gets_a_different_identity(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Give a separately initialized installation its own ID."""
    original = await PostgresInstallationIdentityReader(database).read()

    with temporary_database(temporary_postgres_settings) as new_settings:
        await asyncio.to_thread(run_migrations, new_settings)
        new_database = Database(new_settings)
        try:
            await new_database.startup()
            new_identity = await PostgresInstallationIdentityReader(new_database).read()
        finally:
            await new_database.shutdown()

    assert new_identity != original


@pytest.mark.asyncio
async def test_database_rejects_a_second_installation_identity(
    database: Database,
) -> None:
    """Reject another identity row so one installation cannot acquire conflicting IDs."""
    original = await PostgresInstallationIdentityReader(database).read()

    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            await session.execute(
                insert(InstallationIdentityRow).values(
                    singleton_key=2,
                    installation_id=uuid4(),
                )
            )

    assert await PostgresInstallationIdentityReader(database).read() == original
