"""Check additive profile persistence against the previous PostgreSQL schema."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from tests.support.postgres import database_session
from tests.support.processing_profile_scenarios import profile_command, profile_context
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.bootstrap.processing_profile_composition import (
    open_processing_profile_creation,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_action_grant_row import (
    ProcessingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_creation_result_row import (
    ProcessingProfileCreationResultRow,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_row import (
    ProcessingProfileRow,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    SUPPORTED_SCHEMA_REVISION,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

_PREVIOUS = "0036_provider_credentials"
_PROFILE_REVISION = "0037_processing_profiles"
_TABLES = {
    "processing_profiles",
    "processing_profile_action_grants",
    "processing_profile_creation_results",
    "processing_profile_grant_operation_results",
}

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


def _config(settings: DatabaseSettings) -> Config:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = settings
    return config


def test_empty_schema_upgrade_and_downgrade_preserve_prior_tables(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    config = _config(temporary_postgres_settings)
    command.upgrade(config, _PREVIOUS)
    with database_session(temporary_postgres_settings) as session:
        previous_tables = set(inspect(session.connection()).get_table_names())
        assert _TABLES.isdisjoint(previous_tables)

    command.upgrade(config, _PROFILE_REVISION)
    with database_session(temporary_postgres_settings) as session:
        schema = inspect(session.connection())
        assert set(schema.get_table_names()) == previous_tables | _TABLES
        assert session.scalar(select(AlembicVersionRow.version_num)) == _PROFILE_REVISION
        assert {"uq_processing_profiles_project_name", "uq_processing_profiles_scope_id"}.issubset(
            {key["name"] for key in schema.get_unique_constraints("processing_profiles")}
        )
        for table_name, foreign_key, columns in (
            (
                "processing_profile_action_grants",
                "processing_profiles",
                ("project_id", "processing_profile_id"),
            ),
            (
                "processing_profile_action_grants",
                "project_memberships",
                ("project_id", "recipient_principal_id", "recipient_kind"),
            ),
            (
                "processing_profile_creation_results",
                "processing_profiles",
                ("organization_id", "project_id", "processing_profile_id"),
            ),
            (
                "processing_profile_creation_results",
                "idempotency_reservations",
                ("operation_id", "organization_id", "project_id", "creator_principal_id"),
            ),
        ):
            assert (foreign_key, columns) in {
                (key["referred_table"], tuple(key["constrained_columns"]))
                for key in schema.get_foreign_keys(table_name)
            }

    command.downgrade(config, _PREVIOUS)
    with database_session(temporary_postgres_settings) as session:
        assert session.scalar(select(AlembicVersionRow.version_num)) == _PREVIOUS
        assert set(inspect(session.connection()).get_table_names()) == previous_tables


@pytest.mark.asyncio
async def test_retained_profile_and_original_reject_downgrade(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    project_id = (await create_project(database, seed)).project.project_id
    fingerprints = RequestFingerprintService(RequestFingerprintKey(b"P" * 32))
    async with open_processing_profile_creation(database, fingerprints) as creator:
        result = await creator.create(
            access=seed.access,
            command=profile_command(project_id),
            context=profile_context(project_id, "migration-original"),
        )

    with pytest.raises(RuntimeError, match="Retained Processing Profiles"):
        command.downgrade(_config(temporary_postgres_settings), _PREVIOUS)

    profile_id = result.profile.id.value
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        )
        assert await session.get(ProcessingProfileRow, profile_id) is not None
        receipt = await session.get(
            ProcessingProfileCreationResultRow, result.operation.operation_id.value
        )
        assert receipt is not None and receipt.processing_profile_id == profile_id
        assignments = await session.scalars(
            select(ProcessingProfileActionGrantRow).where(
                ProcessingProfileActionGrantRow.processing_profile_id == profile_id
            )
        )
        assert {(row.recipient_principal_id, row.action, row.can_grant) for row in assignments} == {
            (seed.access.actor_principal_id.value, action.value, True)
            for action in ProcessingProfileAction
        }
