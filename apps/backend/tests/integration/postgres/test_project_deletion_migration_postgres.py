"""Qualify deletion backing without changing the delivered upload-default representation."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from tests.integration.access.test_project_deletion_postgres import (
    admit_deletion,
    seed_deletion_scenario,
)

from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.project_upload_default_group_row import (
    ProjectUploadDefaultGroupRow,
)
from inframeld_backend.access.infrastructure.rows.project_upload_default_result_row import (
    ProjectUploadDefaultResultRow,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


def configuration(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


async def test_real_deletion_storage_and_indexed_handoff_exist(database: Database) -> None:
    async with database.session() as session:
        connection = await session.connection()
        assert await connection.run_sync(
            lambda sync: inspect(sync).has_table("project_deletion_obligations")
        )
        columns = await connection.run_sync(lambda sync: inspect(sync).get_columns("durable_jobs"))
        assert "deletion_obligation_id" in {column["name"] for column in columns}
        indexes = await connection.run_sync(
            lambda sync: inspect(sync).get_indexes("project_deletion_obligations")
        )
        assert any(
            index["column_names"] == ["admitted_at", "id"]
            and "postgresql_where" in index.get("dialect_options", {})
            for index in indexes
        )


@pytest.mark.parametrize(
    "wrong", ["missing-parent", "other-project", "other-organization", "artifact-binding"]
)
async def test_child_requires_exact_scoped_genuine_deletion_parent(
    database: Database, wrong: str
) -> None:
    scope = await seed_deletion_scenario(database)
    accepted = await admit_deletion(database, scope)
    async with database.session() as session, session.begin():
        row = await session.get(DurableJobRow, accepted.job_id.value)
        assert row is not None
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                match wrong:
                    case "missing-parent":
                        row.deletion_obligation_id = uuid4()
                    case "other-project":
                        row.project_id = scope.other_project.value
                    case "other-organization":
                        row.organization_id = uuid4()
                    case _:
                        row.binding_kind = "artifact_cleanup"
                await session.flush()


@pytest.mark.parametrize("wrong", ["negative-before", "too-large-after", "wrong-admission-delta"])
async def test_original_revision_shape_is_enforced_by_postgres(
    database: Database, wrong: str
) -> None:
    scope = await seed_deletion_scenario(database)
    accepted = await admit_deletion(database, scope)
    async with database.session() as session, session.begin():
        row = await session.get(ProjectDeletionObligationRow, accepted.obligation_id.value)
        assert row is not None
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                if wrong == "negative-before":
                    row.before_access_revision = -1
                elif wrong == "too-large-after":
                    row.access_revision = 9007199254740992
                else:
                    row.access_revision = row.before_access_revision + 2
                await session.flush()


async def test_retained_parent_blocks_downgrade_without_erasing_default_history(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    scope = await seed_deletion_scenario(database)
    accepted = await admit_deletion(database, scope)
    with pytest.raises(RuntimeError, match="[Pp]roject.*deletion|deletion.*[Pp]roject"):
        command.downgrade(
            configuration(temporary_postgres_settings), "0030_project_upload_defaults"
        )
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0033_stranded_authority_repair"
        )
        assert (
            await session.get(ProjectDeletionObligationRow, accepted.obligation_id.value)
            is not None
        )
        assert list(await session.scalars(select(ProjectUploadDefaultGroupRow.group_id)))
        assert list(await session.scalars(select(ProjectUploadDefaultResultRow.operation_id)))


async def test_empty_deletion_downgrade_preserves_actual0030_links_groups_and_history(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    await seed_deletion_scenario(database)
    async with database.session() as session:
        groups = tuple(await session.scalars(select(AccessGroupRow.id).order_by(AccessGroupRow.id)))
        links = tuple(
            await session.scalars(
                select(ProjectUploadDefaultGroupRow.group_id).order_by(
                    ProjectUploadDefaultGroupRow.group_id
                )
            )
        )
        originals = tuple(
            await session.scalars(
                select(ProjectUploadDefaultResultRow.operation_id).order_by(
                    ProjectUploadDefaultResultRow.operation_id
                )
            )
        )
    command.downgrade(configuration(temporary_postgres_settings), "0030_project_upload_defaults")
    command.upgrade(configuration(temporary_postgres_settings), "head")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0033_stranded_authority_repair"
        )
        assert (
            tuple(await session.scalars(select(AccessGroupRow.id).order_by(AccessGroupRow.id)))
            == groups
        )
        assert (
            tuple(
                await session.scalars(
                    select(ProjectUploadDefaultGroupRow.group_id).order_by(
                        ProjectUploadDefaultGroupRow.group_id
                    )
                )
            )
            == links
        )
        assert (
            tuple(
                await session.scalars(
                    select(ProjectUploadDefaultResultRow.operation_id).order_by(
                        ProjectUploadDefaultResultRow.operation_id
                    )
                )
            )
            == originals
        )
        assert list(await session.scalars(select(ProjectDeletionObligationRow.id))) == []
