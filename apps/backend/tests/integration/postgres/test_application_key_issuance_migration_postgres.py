"""Qualify fixed adapter bindings and lossless issuance-history migration."""

import os
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import (
    ARRAY,
    DateTime,
    LargeBinary,
    String,
    Text,
    Uuid,
    column,
    func,
    insert,
    inspect,
    select,
    table,
    update,
)
from sqlalchemy.exc import IntegrityError
from tests.support.application_key_scenarios import seed_application_key
from tests.support.postgres import database_session

from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.infrastructure.migrations.migration_runner import ALEMBIC_CONFIG_PATH
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


@pytest.mark.asyncio
async def test_fixed_bindings_and_safe_original_storage_are_available(database: Database) -> None:
    async with database.session() as session:
        connection = await session.connection()
        columns = await connection.run_sync(
            lambda sync: frozenset(
                str(column["name"]) for column in inspect(sync).get_columns("application_keys")
            )
        )
        assert {"http_audience", "mcp_audience"} <= columns, (
            "Application keys still lack their independent fixed adapter bindings."
        )
        assert "audience" not in columns
        assert await connection.run_sync(
            lambda sync: inspect(sync).has_table("application_key_issuance_results")
        )
        original_columns = await connection.run_sync(
            lambda sync: frozenset(
                str(column["name"])
                for column in inspect(sync).get_columns("application_key_issuance_results")
            )
        )
    assert original_columns == {
        "operation_id",
        "organization_id",
        "project_id",
        "application_principal_id",
        "installation_id",
        "issuer_principal_id",
        "key_id",
        "allowed_adapters",
        "created_at",
        "expires_at",
        "revoked_at",
        "before_revision",
        "access_revision",
    }


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


@pytest.mark.parametrize("adapters", [("http",), ("mcp",), ("http", "mcp"), ("mcp", "http")])
def test_legacy_audience_is_copied_literally_without_expanding_adapters_and_round_trips(
    temporary_postgres_settings: DatabaseSettings, adapters: tuple[str, ...]
) -> None:
    settings = temporary_postgres_settings
    config = _config(settings)
    command.upgrade(config, "0027_invitations")
    organization, project, application, key_id = uuid4(), uuid4(), uuid4(), uuid4()
    audience = "https://literal.test/resource?path=%2F"
    created = datetime(2020, 1, 1, tzinfo=UTC)
    expires = created + timedelta(days=365)
    revoked = created + timedelta(days=1)
    legacy = table(
        "application_keys",
        column("key_id", Uuid()),
        column("organization_id", Uuid()),
        column("project_id", Uuid()),
        column("application_principal_id", Uuid()),
        column("installation_id", Uuid()),
        column("audience", Text()),
        column("allowed_adapters", ARRAY(String(8))),
        column("verifier", LargeBinary()),
        column("created_at", DateTime(timezone=True)),
        column("expires_at", DateTime(timezone=True)),
        column("revoked_at", DateTime(timezone=True)),
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
                    display_name="Legacy",
                ),
            ]
        )
        session.flush()
        session.add(
            ApplicationAccountRow(
                principal_id=application,
                organization_id=organization,
                project_id=project,
                principal_kind=PrincipalKind.APPLICATION,
            )
        )
        session.flush()
        installed = session.scalar(select(InstallationIdentityRow.installation_id))
        assert installed is not None
        session.execute(
            insert(legacy).values(
                key_id=key_id,
                organization_id=organization,
                project_id=project,
                application_principal_id=application,
                installation_id=installed,
                audience=audience,
                allowed_adapters=list(adapters),
                verifier=b"V" * 32,
                created_at=created,
                expires_at=expires,
                revoked_at=revoked,
            )
        )
    for _ in range(2):
        command.upgrade(config, "head")
        with database_session(settings) as session:
            key = session.get(ApplicationKeyRow, key_id)
            assert key is not None
            assert key.http_audience == (audience if "http" in adapters else None)
            assert key.mcp_audience == (audience if "mcp" in adapters else None)
            assert tuple(key.allowed_adapters) == adapters
            assert key.verifier == b"V" * 32 and key.created_at == created
            assert key.expires_at == expires and key.revoked_at == revoked
            assert (
                session.scalar(
                    select(func.count())
                    .select_from(ProjectMembershipRow)
                    .where(ProjectMembershipRow.principal_id == application)
                )
                == 0
            )
        command.downgrade(config, "0027_invitations")
        with database_session(settings) as session:
            row = (
                session.execute(
                    select(legacy.c.audience, legacy.c.allowed_adapters, legacy.c.verifier).where(
                        legacy.c.key_id == key_id
                    )
                )
                .tuples()
                .one()
            )
            assert row == (audience, list(adapters), b"V" * 32)
    command.upgrade(config, "head")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "invalid", ["missing-http", "extra-mcp", "blank-http", "missing-mcp", "extra-http", "blank-mcp"]
)
async def test_selected_slots_are_nonnull_nonblank_and_unselected_slots_remain_null(
    database: Database, invalid: str
) -> None:
    seed = await seed_application_key(database)
    async with database.session() as session, session.begin():
        statement = update(ApplicationKeyRow).where(
            ApplicationKeyRow.key_id == seed.credential.key_id.value
        )
        if invalid == "missing-http":
            statement = statement.values(http_audience=None)
        elif invalid == "extra-mcp":
            statement = statement.values(mcp_audience="https://mcp.test/mcp")
        elif invalid == "blank-http":
            statement = statement.values(http_audience=" ")
        elif invalid == "missing-mcp":
            statement = statement.values(
                allowed_adapters=["mcp"], http_audience=None, mcp_audience=None
            )
        elif invalid == "extra-http":
            statement = statement.values(
                allowed_adapters=["mcp"], mcp_audience="https://mcp.test/mcp"
            )
        else:
            statement = statement.values(
                allowed_adapters=["mcp"], http_audience=None, mcp_audience=" "
            )
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(statement)
    async with database.session() as session:
        key = await session.get(ApplicationKeyRow, seed.credential.key_id.value)
        assert key is not None and key.allowed_adapters == ["http"]
        assert key.http_audience == "https://api.test" and key.mcp_audience is None


@pytest.mark.asyncio
@pytest.mark.parametrize("lifecycle", ["active", "expired", "revoked"])
async def test_unequal_dual_bindings_refuse_downgrade_before_any_data_loss(
    database: Database, temporary_postgres_settings: DatabaseSettings, lifecycle: str
) -> None:
    seed = await seed_application_key(
        database, adapters=(ApplicationKeyAdapter.HTTP, ApplicationKeyAdapter.MCP)
    )
    async with database.session() as session, session.begin():
        key = await session.get(ApplicationKeyRow, seed.credential.key_id.value)
        assert key is not None
        key.mcp_audience = "https://mcp.test/mcp"
        if lifecycle == "expired":
            key.expires_at = key.created_at + timedelta(microseconds=1)
        if lifecycle == "revoked":
            key.revoked_at = key.created_at
        await session.flush()
        if lifecycle == "expired":
            checked = await session.scalar(
                select(func.clock_timestamp(type_=DateTime(timezone=True)))
            )
            assert checked is not None and key.expires_at <= checked
    with pytest.raises(RuntimeError, match="Unequal application-key adapter bindings"):
        command.downgrade(_config(temporary_postgres_settings), "0027_invitations")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num))
            == "0030_stranded_authority_repair"
        )
        key = await session.get(ApplicationKeyRow, seed.credential.key_id.value)
        assert (
            key is not None
            and key.mcp_audience == "https://mcp.test/mcp"
            and key.http_audience == "https://api.test"
        )
