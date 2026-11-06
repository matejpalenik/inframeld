"""Keep exact revisions and original receipts through range migration and exhaustion."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from tests.support.postgres import database_connection
from tests.support.project_action_grant_postgres_scenarios import (
    change_project_grant,
    seed_project_grant_recipients,
)

from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_operation_result_row import (
    ProjectActionGrantOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
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
_MAX = 2**53 - 1


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


async def test_access_revisions_cross_int32_and_reach_maximum_without_wrapping(
    database: Database,
) -> None:
    seed = await seed_project_grant_recipients(database)
    async with database.session() as session, session.begin():
        await session.execute(update(ProjectRow).values(access_revision=2**31 - 1))
    wide = await change_project_grant(database, seed, revision=2**31 - 1, key="cross-int32")
    assert wide.access_revision == 2**31
    async with database.session() as session, session.begin():
        await session.execute(update(ProjectRow).values(access_revision=_MAX - 1))
    original = await change_project_grant(
        database, seed, revision=_MAX - 1, key="last-change", can_grant=True
    )
    assert original.access_revision == _MAX
    unchanged = await change_project_grant(
        database, seed, revision=_MAX, key="maximum-noop", can_grant=True
    )
    assert not unchanged.changed and unchanged.access_revision == _MAX
    recovered = await change_project_grant(
        database, seed, revision=_MAX - 1, key="last-change", can_grant=True
    )
    assert recovered.operation.operation_id == original.operation.operation_id
    assert recovered.access_revision == _MAX and not recovered.operation.created
    with pytest.raises(ConflictError):
        await change_project_grant(database, seed, revision=_MAX, key="overflow", removing=True)
    async with database.session() as session:
        assert await session.scalar(select(ProjectRow.access_revision)) == _MAX
        grant = await session.get(
            ProjectActionGrantRow,
            (seed.project.project_id.value, seed.bob_id.value, "inspect-budget"),
        )
        assert grant is not None and grant.can_grant
        receipts = (await session.scalars(select(ProjectActionGrantOperationResultRow))).all()
        assert len(receipts) == 3


async def test_database_refuses_out_of_range_counter_without_truncation(database: Database) -> None:
    await seed_project_grant_recipients(database)
    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            await session.execute(update(ProjectRow).values(access_revision=_MAX + 1))
    async with database.session() as session:
        assert await session.scalar(select(ProjectRow.access_revision)) == 2


async def test_unsafe_downgrade_preserves_current_schema_and_exact_revision(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    await seed_project_grant_recipients(database)
    async with database.session() as session, session.begin():
        await session.execute(update(ProjectRow).values(access_revision=2**31))
    with pytest.raises(RuntimeError, match="previous integer"):
        command.downgrade(_config(temporary_postgres_settings), "0022_project_grant_results")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0025_access_group_administration"
        )
        assert await session.scalar(select(ProjectRow.access_revision)) == 2**31


async def test_upgrade_rejects_wide_retained_receipt_without_rewriting_history(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_grant_recipients(database)
    original = await change_project_grant(database, seed, revision=2, key="retained")
    config = _config(temporary_postgres_settings)
    command.downgrade(config, "0022_project_grant_results")
    async with database.session() as session, session.begin():
        await session.execute(
            update(ProjectActionGrantOperationResultRow)
            .where(
                ProjectActionGrantOperationResultRow.operation_id
                == original.operation.operation_id.value
            )
            .values(before_revision=_MAX + 1, access_revision=_MAX + 2)
        )
    with pytest.raises(RuntimeError, match="Stored revisions exceed"):
        command.upgrade(config, "head")
    with database_connection(temporary_postgres_settings) as connection:
        assert (
            connection.scalar(select(AlembicVersionRow.version_num)) == "0022_project_grant_results"
        )
        assert (
            connection.scalar(select(ProjectActionGrantOperationResultRow.access_revision))
            == _MAX + 2
        )


async def test_valid_revision_migration_preserves_original_receipt_and_replay(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_grant_recipients(database)
    original = await change_project_grant(database, seed, revision=2, key="retained")
    config = _config(temporary_postgres_settings)
    command.downgrade(config, "0022_project_grant_results")
    command.upgrade(config, "head")
    recovered = await change_project_grant(database, seed, revision=2, key="retained")
    assert recovered.operation.operation_id == original.operation.operation_id
    assert (recovered.access_revision, recovered.changed) == (3, True)


async def test_upgrade_rejects_wide_audit_revision_without_rewriting_history(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_grant_recipients(database)
    original = await change_project_grant(database, seed, revision=2, key="audit-retained")
    config = _config(temporary_postgres_settings)
    command.downgrade(config, "0022_project_grant_results")
    async with database.session() as session, session.begin():
        await session.execute(
            update(AccessAuditEventRow)
            .where(AccessAuditEventRow.correlation_id == original.operation.operation_id.value)
            .values(after_values={"revision": _MAX + 1})
        )
    with pytest.raises(RuntimeError, match="Stored audit revisions exceed"):
        command.upgrade(config, "head")
    with database_connection(temporary_postgres_settings) as connection:
        assert (
            connection.scalar(select(AlembicVersionRow.version_num)) == "0022_project_grant_results"
        )
        assert connection.scalar(
            select(AccessAuditEventRow.after_values).where(
                AccessAuditEventRow.correlation_id == original.operation.operation_id.value
            )
        ) == {"revision": _MAX + 1}
