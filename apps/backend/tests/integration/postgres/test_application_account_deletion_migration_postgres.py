"""Exercise real retirement-original storage and migration lifecycle."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from tests.support.application_key_scenarios import issue_application_key

from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_retirement_original_storage_is_available(database: Database) -> None:
    async with database.session() as session:
        connection = await session.connection()
        assert await connection.run_sync(
            lambda sync: inspect(sync).has_table("application_account_deletion_results")
        ), "Application retirement has no retained original storage."
        columns = await connection.run_sync(
            lambda sync: frozenset(
                str(column["name"])
                for column in inspect(sync).get_columns("application_account_deletion_results")
            )
        )
    assert columns == {
        "operation_id",
        "installation_id",
        "organization_id",
        "project_id",
        "actor_principal_id",
        "application_principal_id",
        "before_revision",
        "access_revision",
    }


async def test_empty_retirement_history_round_trips_without_changing_live_account(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    _, issued = await issue_application_key(database)
    metadata = issued.original.metadata
    async with database.session() as session:
        account = await session.get(ApplicationAccountRow, metadata.application_principal_id.value)
        principal = await session.get(PrincipalRow, metadata.application_principal_id.value)
        key = await session.get(ApplicationKeyRow, metadata.key_id.value)
        assert account is not None and principal is not None and key is not None
        before = (account.resource_name, principal.status, key.revoked_at, key.verifier)
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings
    command.downgrade(config, "0031_project_deletion")
    command.upgrade(config, "head")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0032_application_retirement"
        )
        account = await session.get(ApplicationAccountRow, metadata.application_principal_id.value)
        principal = await session.get(PrincipalRow, metadata.application_principal_id.value)
        key = await session.get(ApplicationKeyRow, metadata.key_id.value)
        assert account is not None and principal is not None and key is not None
        assert (account.resource_name, principal.status, key.revoked_at, key.verifier) == before
