"""Require reservation-bound original grant results without a live assignment link."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.postgres import database_connection
from tests.support.project_action_grant_postgres_scenarios import (
    change_project_grant,
    seed_project_grant_recipients,
)

from inframeld_backend.access.infrastructure.rows.project_action_grant_operation_result_row import (
    ProjectActionGrantOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    SUPPORTED_SCHEMA_REVISION,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def test_original_grant_results_have_no_dependency_on_live_grants_or_memberships(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    with database_connection(temporary_postgres_settings) as connection:
        schema = inspect(connection)
        assert schema.has_table("project_action_grant_operation_results")
        foreign_keys = schema.get_foreign_keys("project_action_grant_operation_results")
        assert any(key["referred_table"] == "idempotency_reservations" for key in foreign_keys)
        assert all(
            key["referred_table"] not in {"project_action_grants", "project_memberships"}
            for key in foreign_keys
        )
        columns = {
            column["name"]
            for column in schema.get_columns("project_action_grant_operation_results")
        }
        assert columns == {
            "operation_id",
            "installation_id",
            "organization_id",
            "project_id",
            "actor_principal_id",
            "recipient_principal_id",
            "action_id",
            "change_kind",
            "before_revision",
            "access_revision",
            "changed",
            "status_code",
            "before_can_grant",
            "can_grant",
        }


@pytest.mark.parametrize(
    "corruption",
    [
        "installation",
        "organization",
        "project",
        "actor",
        "recipient",
        "kind",
        "before-revision",
        "after-revision",
        "status",
        "level",
    ],
)
async def test_receipt_constraints_reject_unbound_scope_and_incoherent_business_outcomes(
    database: Database, corruption: str
) -> None:
    seed = await seed_project_grant_recipients(database)
    result = await change_project_grant(database, seed, revision=2, key="original")
    changes: dict[str, object]
    if corruption in {"installation", "organization", "project"}:
        changes = {f"{corruption}_id": uuid4()}
    elif corruption == "actor":
        changes = {"actor_principal_id": seed.bob_id.value}
    elif corruption == "recipient":
        changes = {"recipient_principal_id": uuid4()}
    elif corruption == "kind":
        changes = {"change_kind": "unknown"}
    elif corruption == "before-revision":
        changes = {"before_revision": -1}
    elif corruption == "after-revision":
        changes = {"access_revision": 2}
    elif corruption == "status":
        changes = {"status_code": 200}
    else:
        changes = {"can_grant": None}
    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            await session.execute(
                update(ProjectActionGrantOperationResultRow)
                .where(
                    ProjectActionGrantOperationResultRow.operation_id
                    == result.operation.operation_id.value
                )
                .values(**changes)
            )
    async with database.session() as session:
        row = await session.get(
            ProjectActionGrantOperationResultRow, result.operation.operation_id.value
        )
        assert (
            row is not None
            and row.access_revision == 3
            and row.status_code == 201
            and row.can_grant is False
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 3


async def test_retained_original_receipt_refuses_downgrade_and_keeps_schema_and_result(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_grant_recipients(database)
    original = await change_project_grant(database, seed, revision=2, key="retained-original")
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings
    with pytest.raises(RuntimeError, match="Retained grant outcomes"):
        command.downgrade(config, "0021_job_effect_observations")
    with database_connection(temporary_postgres_settings) as connection:
        assert inspect(connection).has_table("project_action_grant_operation_results")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        )
        row = await session.get(
            ProjectActionGrantOperationResultRow, original.operation.operation_id.value
        )
        assert (
            row is not None
            and row.access_revision == 3
            and row.status_code == 201
            and row.can_grant is False
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 3
    recovered = await change_project_grant(database, seed, revision=2, key="retained-original")
    assert recovered.operation.operation_id == original.operation.operation_id
    assert (recovered.status_code, recovered.access_revision, recovered.changed) == (201, 3, True)
