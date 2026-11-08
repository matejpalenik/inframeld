"""Preserve legacy identities and protect new retained account and credential records."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Text, Uuid, column, func, insert, select, table, update
from sqlalchemy.exc import IntegrityError
from tests.support.application_account_scenarios import create_account
from tests.support.postgres import database_session
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.application_account_creation_result_row import (
    ApplicationAccountCreationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_name_reservation_row import (
    ApplicationAccountNameReservationRow,
)
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.readers.postgres_installation_identity_reader import (
    PostgresInstallationIdentityReader,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


def test_upgrade_preserves_unnamed_legacy_application_and_round_trips_empty_additions(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    settings = temporary_postgres_settings
    config = _config(settings)
    command.upgrade(config, "0023_safe_numeric_revisions")
    organization, project, application = uuid4(), uuid4(), uuid4()
    legacy_label = " old unrestricted\nlabel "
    # This historical schema predates resource_name, so use its explicit typed
    # table columns rather than today's extension mapping.
    legacy = table(
        "application_accounts",
        column("principal_id", Uuid()),
        column("organization_id", Uuid()),
        column("project_id", Uuid()),
        column("principal_kind", Text()),
    )
    with database_session(settings) as session, session.begin():
        session.add(OrganizationRow(id=organization, name="Legacy"))
        session.flush()
        session.add_all(
            [
                ProjectRow(
                    id=project,
                    organization_id=organization,
                    name="Legacy",
                    status=ProjectStatus.ACTIVE,
                ),
                PrincipalRow(
                    id=application,
                    organization_id=organization,
                    kind=PrincipalKind.APPLICATION,
                    status=PrincipalStatus.ACTIVE,
                    display_name=legacy_label,
                ),
            ]
        )
        session.flush()
        session.execute(
            insert(legacy).values(
                principal_id=application,
                organization_id=organization,
                project_id=project,
                principal_kind="application",
            )
        )
        session.add(
            ProjectMembershipRow(
                project_id=project,
                principal_id=application,
                organization_id=organization,
                principal_kind=PrincipalKind.APPLICATION,
                application_principal_id=application,
            )
        )
    for _ in range(2):
        command.upgrade(config, "head")
        with database_session(settings) as session:
            account = session.get(ApplicationAccountRow, application)
            principal = session.get(PrincipalRow, application)
            assert (
                account is not None
                and account.resource_name is None
                and account.project_id == project
            )
            assert principal is not None and principal.display_name == legacy_label
            for model in (
                ApplicationAccountNameReservationRow,
                ApplicationAccountCreationResultRow,
                ApplicationKeyRow,
            ):
                assert session.scalar(select(func.count()).select_from(model)) == 0
        command.downgrade(config, "0023_safe_numeric_revisions")
        # The historical predicate admits NULL for application rows. Preserve
        # that downgrade behavior, then restore the valid binding before upgrade.
        with database_session(settings) as session, session.begin():
            membership = update(ProjectMembershipRow).where(
                ProjectMembershipRow.project_id == project,
                ProjectMembershipRow.principal_id == application,
            )
            session.execute(membership.values(application_principal_id=None))
        with database_session(settings) as session:
            member = session.get(ProjectMembershipRow, (project, application))
            assert member is not None and member.application_principal_id is None
        with database_session(settings) as session, session.begin():
            session.execute(membership.values(application_principal_id=application))
    command.upgrade(config, "head")


@pytest.mark.asyncio
async def test_retained_account_outcome_prevents_destructive_downgrade(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    created = await create_account(database, seed.access, project.project_id)
    with pytest.raises(RuntimeError, match="Retained application"):
        command.downgrade(_config(temporary_postgres_settings), "0023_safe_numeric_revisions")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0028_application_key_issuance"
        )
        assert (
            await session.get(
                ApplicationAccountCreationResultRow, created.operation.operation_id.value
            )
            is not None
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid",
    [
        "digest",
        "empty-adapters",
        "duplicate-adapters",
        "unknown-adapter",
        "scope",
        "expiry",
        "audience",
    ],
)
async def test_key_storage_rejects_unsafe_record_shapes_and_wrong_project(
    database: Database, invalid: str
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    account = (await create_account(database, seed.access, project.project_id)).account
    installed = await PostgresInstallationIdentityReader(database).read()
    row = ApplicationKeyRow(
        key_id=uuid4(),
        organization_id=seed.organization_id.value,
        project_id=project.project_id.value,
        application_principal_id=account.principal_id.value,
        installation_id=installed.value,
        http_audience="https://api.test",
        mcp_audience=None,
        allowed_adapters=["http"],
        verifier=b"V" * 32,
        expires_at=datetime.now(UTC) + timedelta(days=90),
    )
    if invalid == "digest":
        row.verifier = b"V" * 31
    elif invalid == "empty-adapters":
        row.allowed_adapters = []
    elif invalid == "duplicate-adapters":
        row.allowed_adapters = ["http", "http"]
    elif invalid == "unknown-adapter":
        row.allowed_adapters = ["other"]
    elif invalid == "scope":
        other = (await create_project(database, seed, name="other", key="other-project")).project
        row.project_id = other.project_id.value
    elif invalid == "expiry":
        row.expires_at = datetime.now(UTC) - timedelta(days=1)
    else:
        row.http_audience = " "
    with pytest.raises(IntegrityError):
        async with database.session() as session, session.begin():
            session.add(row)
            await session.flush()
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ApplicationKeyRow)) == 0
