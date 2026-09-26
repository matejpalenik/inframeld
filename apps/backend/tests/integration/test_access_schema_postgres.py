"""Check that PostgreSQL migrations create the Access foundation."""

import os

import psycopg
import pytest

from inframeld_backend.shared.infrastructure.migrations import run_migrations
from inframeld_backend.shared.infrastructure.settings import DatabaseSettings

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

    with psycopg.connect(
        host=temporary_postgres_settings.host,
        port=temporary_postgres_settings.port,
        dbname=temporary_postgres_settings.name,
        user=temporary_postgres_settings.user,
        password=temporary_postgres_settings.password.get_secret_value(),
    ) as connection:
        rows = connection.execute(
            """
            SELECT tablename
            FROM pg_catalog.pg_tables
            WHERE schemaname = 'public'
            """
        ).fetchall()

    actual_tables = {row[0] for row in rows}
    missing_tables = ACCESS_FOUNDATION_TABLES - actual_tables

    assert not missing_tables, f"Missing Access tables: {sorted(missing_tables)}"
