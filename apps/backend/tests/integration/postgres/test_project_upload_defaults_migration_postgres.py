"""Qualify real scoped links and retained originals without a second default representation."""

import os
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from tests.support.project_upload_default_scenarios import (
    UploadDefaultScenario,
    seed_upload_default_scenario,
)

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.project_upload_default_group_row import (
    ProjectUploadDefaultGroupRow,
)
from inframeld_backend.access.infrastructure.rows.project_upload_default_result_row import (
    ProjectUploadDefaultResultRow,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


@pytest_asyncio.fixture
async def scope(database: Database) -> UploadDefaultScenario:
    return await seed_upload_default_scenario(database)


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


def _original(scope: UploadDefaultScenario) -> ProjectUploadDefaultResultRow:
    return ProjectUploadDefaultResultRow(
        operation_id="retained-upload-default",
        organization_id=scope.actor.organization_id.value,
        project_id=scope.project_id.value,
        actor_principal_id=scope.actor.access.actor_principal_id.value,
        before_revision=scope.revision,
        access_revision=scope.revision + 1,
        before_group_ids=None,
        group_ids=[scope.groups[0].group_id.value],
    )


def _parent(scope: UploadDefaultScenario) -> IdempotencyReservationRow:
    parent = IdempotencyReservationRow(
        operation_id="retained-upload-default",
        organization_id=scope.actor.organization_id.value,
        project_id=scope.project_id.value,
        principal_id=scope.actor.access.actor_principal_id.value,
        method="PUT",
        requested_route=f"/v1/projects/{scope.project_id.value}/upload-defaults",
        request_key="retained",
        request_fingerprint=b"f" * 32,
        replay_kind=OperationReplayKind.SAFE_RESULT,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )
    parent.state = OperationReservationState.REPLAYABLE
    return parent


async def test_storage_lifecycle_is_available(database: Database) -> None:
    async with database.session() as session:
        connection = await session.connection()
        assert await connection.run_sync(
            lambda sync: inspect(sync).has_table("project_upload_default_groups")
        )
        assert await connection.run_sync(
            lambda sync: inspect(sync).has_table("project_upload_default_results")
        )


@pytest.mark.parametrize("wrong", ["organization", "project", "group"])
async def test_live_default_references_are_exactly_project_scoped(
    database: Database, scope: UploadDefaultScenario, wrong: str
) -> None:
    foreign_project, foreign_group = uuid4(), uuid4()
    async with database.session() as session, session.begin():
        session.add(
            ProjectRow(
                id=foreign_project,
                organization_id=scope.actor.organization_id.value,
                name="Other",
                status=ProjectStatus.ACTIVE,
            )
        )
        await session.flush()
        session.add(AccessGroupRow(id=foreign_group, project_id=foreign_project, name="OtherGroup"))
    async with database.session() as session, session.begin():
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(
                    ProjectUploadDefaultGroupRow(
                        organization_id=uuid4()
                        if wrong == "organization"
                        else scope.actor.organization_id.value,
                        project_id=foreign_project
                        if wrong == "project"
                        else scope.project_id.value,
                        group_id=foreign_group
                        if wrong == "group"
                        else scope.groups[0].group_id.value,
                    )
                )
                await session.flush()


@pytest.mark.parametrize("wrong", ["absent-parent", "actor", "project"])
async def test_original_requires_its_exact_reservation_namespace(
    database: Database, scope: UploadDefaultScenario, wrong: str
) -> None:
    async with database.session() as session, session.begin():
        if wrong != "absent-parent":
            session.add(_parent(scope))
            await session.flush()
        row = _original(scope)
        if wrong == "actor":
            row.actor_principal_id = scope.bob_id.value
        elif wrong == "project":
            row.project_id = uuid4()
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(row)
                await session.flush()


@pytest.mark.parametrize(
    "wrong", ["negative", "too-large", "wrong-delta", "empty-after", "empty-before", "null-element"]
)
async def test_original_shape_and_revision_constraints_fail_closed(
    database: Database, scope: UploadDefaultScenario, wrong: str
) -> None:
    async with database.session() as session, session.begin():
        session.add(_parent(scope))
        await session.flush()
        row = _original(scope)
        match wrong:
            case "negative":
                row.before_revision = -1
            case "too-large":
                row.access_revision = 9007199254740992
            case "wrong-delta":
                row.access_revision = scope.revision + 2
            case "empty-after":
                row.group_ids = []
            case "empty-before":
                row.before_group_ids = []
            case _:
                row.group_ids = cast(list[UUID], [None])
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                session.add(row)
                await session.flush()


@pytest.mark.parametrize("retained", ["live-default", "original"])
async def test_downgrade_refuses_retained_default_or_original(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    scope: UploadDefaultScenario,
    retained: str,
) -> None:
    async with database.session() as session, session.begin():
        if retained == "live-default":
            session.add(
                ProjectUploadDefaultGroupRow(
                    organization_id=scope.actor.organization_id.value,
                    project_id=scope.project_id.value,
                    group_id=scope.groups[0].group_id.value,
                )
            )
        else:
            session.add(_parent(scope))
            await session.flush()
            session.add(_original(scope))
    with pytest.raises(RuntimeError, match="Retained.*upload"):
        command.downgrade(_config(temporary_postgres_settings), "0029_application_key_revocation")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0033_stranded_authority_repair"
        )
        if retained == "live-default":
            assert (
                await session.get(
                    ProjectUploadDefaultGroupRow,
                    (scope.project_id.value, scope.groups[0].group_id.value),
                )
                is not None
            )
        else:
            assert (
                await session.get(ProjectUploadDefaultResultRow, "retained-upload-default")
                is not None
            )


async def test_empty_upgrade_downgrade_preserves_existing_groups(
    database: Database, temporary_postgres_settings: DatabaseSettings, scope: UploadDefaultScenario
) -> None:
    original_ids = tuple(group.group_id.value for group in scope.groups)
    command.downgrade(_config(temporary_postgres_settings), "0029_application_key_revocation")
    command.upgrade(_config(temporary_postgres_settings), "head")
    async with database.session() as session:
        assert set(
            await session.scalars(
                select(AccessGroupRow.id).where(AccessGroupRow.project_id == scope.project_id.value)
            )
        ) == set(original_ids)
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0033_stranded_authority_repair"
        )
        assert list(await session.scalars(select(ProjectUploadDefaultGroupRow.group_id))) == []
