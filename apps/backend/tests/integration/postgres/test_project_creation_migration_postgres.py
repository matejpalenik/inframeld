"""Preserve existing admission while enforcing retained creation-result integrity."""

import os
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.project_creation_scenarios import (
    INITIAL_ACTIONS,
    create_project,
    seed_project_creator,
)

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.first_administrator_bootstrap_receipt_row import (
    FirstAdministratorBootstrapReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_creation_operation_result_row import (
    ProjectCreationOperationResultRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    BACKEND_ROOT,
    run_migrations,
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


def _configuration(settings: DatabaseSettings) -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.attributes["database_settings"] = settings
    return config


async def test_0016_upgrade_and_empty_outcome_roundtrip_preserve_admission_and_legacy_project(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    legacy_project = uuid4()
    async with database.session() as session, session.begin():
        session.add(
            ProjectRow(
                id=legacy_project,
                organization_id=seed.organization_id.value,
                name="Legacy\nlabel",
                status=ProjectStatus.ACTIVE,
            )
        )
    config = _configuration(temporary_postgres_settings)
    for _ in range(2):
        command.downgrade(config, "0016_first_administrator")
        run_migrations(temporary_postgres_settings)
        async with database.session() as session:
            assert (
                await session.scalar(select(AlembicVersionRow.version_num))
                == "0032_application_retirement"
            )
            receipt = await session.get(
                FirstAdministratorBootstrapReceiptRow, seed.binding.installation_id.value
            )
            assert receipt is not None
            assert (
                receipt.organization_id,
                receipt.recipient_id,
                receipt.before_revision,
                receipt.after_revision,
            ) == (seed.organization_id.value, seed.access.actor_principal_id.value, 0, 1)
            version = await session.get(
                HumanCredentialVersionRow,
                (
                    seed.binding.installation_id.value,
                    seed.binding.identity.authority.value,
                    seed.binding.identity.subject.value,
                ),
            )
            assert version is not None and version.version == seed.binding.version.value
            assert (
                await session.scalar(select(func.count()).select_from(OrganizationActionGrantRow))
                == 4
            )
            project = await session.get(ProjectRow, legacy_project)
            assert project is not None and project.name == "Legacy\nlabel"
            assert project.resource_name is None and (
                project.access_revision,
                project.metadata_revision,
            ) == (0, 0)
            assert (
                await session.scalar(select(func.count()).select_from(ProjectActionGrantRow)) == 0
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(ProjectCreationOperationResultRow)
                )
                == 0
            )


async def test_retained_creation_outcome_refuses_downgrade_without_losing_replay(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    first = await create_project(database, seed)
    with pytest.raises(RuntimeError, match="Retained Project creation outcomes"):
        command.downgrade(_configuration(temporary_postgres_settings), "0016_first_administrator")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0032_application_retirement"
        )
        receipt = await session.get(
            ProjectCreationOperationResultRow, first.operation.operation_id.value
        )
        assert receipt is not None and receipt.project_id == first.project.project_id.value
    replay = await create_project(database, seed)
    assert replay.project == first.project
    assert replay.operation.operation_id == first.operation.operation_id
    assert replay.operation.expires_at == first.operation.expires_at


@pytest.mark.parametrize(
    "corruption",
    ["organization", "actor", "access-revision", "metadata-revision", "initial-actions"],
)
async def test_result_constraints_reject_wrong_original_scope_or_initial_snapshot(
    database: Database, corruption: str
) -> None:
    seed = await seed_project_creator(database)
    first = await create_project(database, seed)
    statement = update(ProjectCreationOperationResultRow).where(
        ProjectCreationOperationResultRow.operation_id == first.operation.operation_id.value
    )
    if corruption == "organization":
        statement = statement.values(organization_id=uuid4())
    elif corruption == "actor":
        statement = statement.values(creator_principal_id=uuid4())
    elif corruption == "access-revision":
        statement = statement.values(access_revision=2)
    elif corruption == "metadata-revision":
        statement = statement.values(metadata_revision=1)
    else:
        statement = statement.values(initial_actions=list(INITIAL_ACTIONS[:-1]))
    async with database.session() as session:
        with pytest.raises(IntegrityError):
            async with session.begin():
                await session.execute(statement)
    replay = await create_project(database, seed)
    assert (
        replay.project == first.project
        and replay.operation.expires_at == first.operation.expires_at
    )
