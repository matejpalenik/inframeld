"""Check that PostgreSQL migrations create the Access foundation."""

import os

import pytest
from sqlalchemy import inspect
from tests.support.postgres import database_connection

from inframeld_backend.shared.infrastructure.migrations.migration_runner import run_migrations
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Set INFRAMELD_RUN_DB_INTEGRATION=1 to run PostgreSQL integration tests",
)

ACCESS_FOUNDATION_TABLES = {
    "organizations",
    "principals",
    "human_identity_links",
    "projects",
    "application_accounts",
    "project_memberships",
    "access_groups",
    "group_memberships",
    "group_managers",
    "organization_action_grants",
    "project_action_grants",
    "group_action_grants",
    "application_action_grants",
    "access_audit_events",
}


def test_migrations_create_access_foundation_tables(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    """Prove migrations create the relational records needed by Access."""
    run_migrations(temporary_postgres_settings)

    with database_connection(temporary_postgres_settings) as connection:
        actual_tables = set(inspect(connection).get_table_names(schema="public"))

    missing_tables = ACCESS_FOUNDATION_TABLES - actual_tables

    assert not missing_tables, f"Missing Access tables: {sorted(missing_tables)}"
