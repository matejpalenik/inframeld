"""Qualify the retained safe receipt required for revocation and original recovery."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select, update
from sqlalchemy.exc import IntegrityError
from tests.support.application_key_scenarios import issue_application_key, revocation_service

from inframeld_backend.access.application.commands.revoke_application_key_command import (
    RevokeApplicationKeyCommand,
)
from inframeld_backend.access.application.dtos.application_key_revocation_result_dto import (
    ApplicationKeyRevocationResultDTO,
)
from inframeld_backend.access.infrastructure.rows.application_key_revocation_result_row import (
    ApplicationKeyRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.application_key_row import ApplicationKeyRow
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
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
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_safe_revocation_original_storage_is_available(database: Database) -> None:
    async with database.session() as session:
        connection = await session.connection()
        assert await connection.run_sync(
            lambda sync: inspect(sync).has_table("application_key_revocation_results")
        ), "Revocation has no retained safe-original storage."
        columns = await connection.run_sync(
            lambda sync: frozenset(
                str(column["name"])
                for column in inspect(sync).get_columns("application_key_revocation_results")
            )
        )
    assert columns == {
        "operation_id",
        "organization_id",
        "project_id",
        "application_principal_id",
        "installation_id",
        "actor_principal_id",
        "key_id",
        "allowed_adapters",
        "created_at",
        "expires_at",
        "revoked_at",
        "before_revision",
        "access_revision",
    }


@pytest_asyncio.fixture
async def revoked_original(database: Database) -> ApplicationKeyRevocationResultDTO:
    creator, issued = await issue_application_key(database)
    metadata = issued.original.metadata
    async with database.session() as session:
        return await revocation_service(session).revoke(
            access=creator,
            command=RevokeApplicationKeyCommand(
                metadata.project_id,
                metadata.application_principal_id,
                metadata.key_id,
                issued.original.access_revision,
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/projects/{metadata.project_id.value}/application-accounts/{metadata.application_principal_id.value}/keys/{metadata.key_id.value}/revoke",
                IdempotencyKey("migration-revoke"),
            ),
        )


@pytest.mark.parametrize(
    "invalid",
    [
        "negative-before",
        "overflow-after",
        "revision-jump",
        "revision-backward",
        "null-revoked",
        "early-revoked",
        "invalid-expiry",
        "null-adapters",
        "empty-adapters",
        "duplicate-adapters",
        "unknown-adapter",
        "actor-scope",
        "account-scope",
        "installation-scope",
    ],
)
async def test_safe_original_constraints_reject_invalid_persisted_outcomes(
    database: Database,
    revoked_original: ApplicationKeyRevocationResultDTO,
    invalid: str,
) -> None:
    operation = revoked_original.operation.operation_id.value
    async with database.session() as session, session.begin():
        original = await session.get(ApplicationKeyRevocationResultRow, operation)
        assert original is not None
        statement = update(ApplicationKeyRevocationResultRow).where(
            ApplicationKeyRevocationResultRow.operation_id == operation
        )
        if invalid == "negative-before":
            statement = statement.values(before_revision=-1)
        elif invalid == "overflow-after":
            statement = statement.values(access_revision=RevisionValidation.MAX_VALUE + 1)
        elif invalid == "revision-jump":
            statement = statement.values(access_revision=original.before_revision + 2)
        elif invalid == "revision-backward":
            statement = statement.values(access_revision=original.before_revision - 1)
        elif invalid == "null-revoked":
            statement = statement.values(revoked_at=None)
        elif invalid == "early-revoked":
            statement = statement.values(revoked_at=original.created_at - timedelta(microseconds=1))
        elif invalid == "invalid-expiry":
            statement = statement.values(expires_at=original.created_at)
        elif invalid == "null-adapters":
            statement = statement.values(allowed_adapters=None)
        elif invalid == "empty-adapters":
            statement = statement.values(allowed_adapters=[])
        elif invalid == "duplicate-adapters":
            statement = statement.values(allowed_adapters=["http", "http"])
        elif invalid == "unknown-adapter":
            statement = statement.values(allowed_adapters=["other"])
        elif invalid == "actor-scope":
            statement = statement.values(actor_principal_id=uuid4())
        elif invalid == "account-scope":
            statement = statement.values(application_principal_id=uuid4())
        else:
            statement = statement.values(installation_id=uuid4())
        with pytest.raises(IntegrityError):
            async with session.begin_nested():
                await session.execute(statement)


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


async def test_empty_revocation_history_round_trips_without_changing_existing_issued_key(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    _, issued = await issue_application_key(database)
    key_id = issued.original.metadata.key_id.value
    async with database.session() as session:
        row = await session.get(ApplicationKeyRow, key_id)
        assert row is not None
        before = (
            row.organization_id,
            row.project_id,
            row.application_principal_id,
            row.installation_id,
            row.http_audience,
            row.mcp_audience,
            row.allowed_adapters,
            row.verifier,
            row.created_at,
            row.expires_at,
            row.revoked_at,
        )
    for _ in range(2):
        command.downgrade(_config(temporary_postgres_settings), "0028_application_key_issuance")
        command.upgrade(_config(temporary_postgres_settings), "head")
        async with database.session() as session:
            row = await session.get(ApplicationKeyRow, key_id)
            assert row is not None
            assert (
                row.organization_id,
                row.project_id,
                row.application_principal_id,
                row.installation_id,
                row.http_audience,
                row.mcp_audience,
                row.allowed_adapters,
                row.verifier,
                row.created_at,
                row.expires_at,
                row.revoked_at,
            ) == before
            assert (
                await session.scalar(select(AlembicVersionRow.version_num))
                == SUPPORTED_SCHEMA_REVISION
            )


async def test_retained_revocation_original_prevents_lossy_downgrade(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    revoked_original: ApplicationKeyRevocationResultDTO,
) -> None:
    with pytest.raises(RuntimeError, match="Retained application-key revocation originals"):
        command.downgrade(_config(temporary_postgres_settings), "0028_application_key_issuance")
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        )
        original = await session.get(
            ApplicationKeyRevocationResultRow, revoked_original.operation.operation_id.value
        )
        assert (
            original is not None
            and original.revoked_at == revoked_original.original.metadata.revoked_at
        )
