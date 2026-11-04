"""Require native receipt storage without changing the existing relationship schema."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, inspect, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.postgres import database_connection
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.infrastructure.rows.project_membership_operation_result_row import (
    ProjectMembershipOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    run_migrations,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires PostgreSQL integration services",
    ),
]


async def test_membership_receipts_are_stored_independently_of_live_membership(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    with database_connection(temporary_postgres_settings) as connection:
        schema = inspect(connection)
        assert schema.has_table("project_membership_operation_results")
        foreign_keys = schema.get_foreign_keys("project_membership_operation_results")
        assert any(key["referred_table"] == "idempotency_reservations" for key in foreign_keys)
        assert all(key["referred_table"] != "project_memberships" for key in foreign_keys)


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
    ],
)
async def test_receipt_constraints_reject_unbound_scope_or_incoherent_original_outcome(
    database: Database, corruption: str
) -> None:
    seed = await seed_membership_project(database)
    added = await change_membership(database, seed, revision=1, key="join")
    changes: dict[str, object]
    if corruption == "installation":
        changes = {"installation_id": uuid4()}
    elif corruption == "organization":
        changes = {"organization_id": uuid4()}
    elif corruption == "project":
        changes = {"project_id": uuid4()}
    elif corruption == "actor":
        changes = {"actor_principal_id": seed.bob_id.value}
    elif corruption == "recipient":
        changes = {"principal_id": uuid4()}
    elif corruption == "kind":
        changes = {"change_kind": "unknown"}
    elif corruption == "before-revision":
        changes = {"before_revision": -1}
    elif corruption == "after-revision":
        changes = {"access_revision": 1}
    else:
        changes = {"status_code": 200}
    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            await session.execute(
                update(ProjectMembershipOperationResultRow)
                .where(
                    ProjectMembershipOperationResultRow.operation_id
                    == added.operation.operation_id.value
                )
                .values(**changes)
            )
    async with database.session() as session:
        original = await session.get(
            ProjectMembershipOperationResultRow, added.operation.operation_id.value
        )
        assert (
            original is not None and original.status_code == 201 and original.access_revision == 2
        )
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is not None
        )


async def test_storage_downgrade_preserves_live_membership_and_refuses_retained_receipts(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_membership_project(database)
    added = await change_membership(database, seed, revision=1, key="join")
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings
    with pytest.raises(RuntimeError, match="Retained membership outcomes"):
        command.downgrade(config, "0019_human_admission")
    async with database.session() as session, session.begin():
        assert (
            await session.get(
                ProjectMembershipOperationResultRow, added.operation.operation_id.value
            )
            is not None
        )
        await session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.operation_id == added.operation.operation_id.value
            )
        )
    command.downgrade(config, "0019_human_admission")
    run_migrations(temporary_postgres_settings)
    async with database.session() as session:
        assert (
            await session.get(
                ProjectMembershipRow, (seed.project.project_id.value, seed.bob_id.value)
            )
            is not None
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 2
        assert (
            await session.scalar(
                select(func.count()).select_from(ProjectMembershipOperationResultRow)
            )
            == 0
        )
