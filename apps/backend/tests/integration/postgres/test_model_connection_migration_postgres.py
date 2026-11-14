"""Preserve the prior Access schema while adding exact model connection bindings."""

import os

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from tests.support.postgres import database_session
from tests.support.project_creation_scenarios import create_project, seed_project_creator

from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_creation_result_row import (
    ModelConnectionCreationResultRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.bootstrap.model_connection_composition import open_model_connection_creation
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    SUPPORTED_SCHEMA_REVISION,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = pytest.mark.skipif(
    os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
    reason="Requires isolated PostgreSQL integration services",
)


def test_model_connection_schema_is_additive_and_has_exact_scope_constraints(
    temporary_postgres_settings: DatabaseSettings,
) -> None:
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings
    command.upgrade(config, "0034_human_lifecycle")
    with database_session(temporary_postgres_settings) as session:
        previous_tables = set(inspect(session.connection()).get_table_names())
        assert "model_connections" not in previous_tables

    command.upgrade(config, "head")
    with database_session(temporary_postgres_settings) as session:
        schema = inspect(session.connection())
        assert session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        assert previous_tables.issubset(schema.get_table_names())
        grants = {
            (fk["referred_table"], tuple(fk["constrained_columns"]))
            for fk in schema.get_foreign_keys("model_connection_action_grants")
        }
        assert ("model_connections", ("project_id", "model_connection_id")) in grants
        assert (
            "project_memberships",
            ("project_id", "recipient_principal_id", "recipient_kind"),
        ) in grants
        assert {"uq_model_connections_project_name", "uq_model_connections_project_id"}.issubset(
            {item["name"] for item in schema.get_unique_constraints("model_connections")}
        )

    command.downgrade(config, "0034_human_lifecycle")
    with database_session(temporary_postgres_settings) as session:
        assert set(inspect(session.connection()).get_table_names()) == previous_tables


@pytest.mark.asyncio
async def test_retained_connection_grants_and_creation_result_prevent_downgrade(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_project_creator(database)
    project_id = (await create_project(database, seed)).project.project_id
    url = "https://models.example.test/v1"
    async with open_model_connection_creation(
        database,
        RequestFingerprintService(RequestFingerprintKey(b"M" * 32)),
        ModelConnectionDestinationSettings(https_base_urls=frozenset({url})),
    ) as creator:
        result = await creator.create(
            access=seed.access,
            command=CreateModelConnectionCommand(
                project_id,
                ResourceName("migration-gateway"),
                SubmittedDisplayName("Migration gateway"),
                ModelConnectionAccessDTO(
                    ModelConnectionProvider.OPENAI_COMPATIBLE,
                    url,
                    None,
                    ModelConnectionAuthentication.API_KEY,
                ),
            ),
            context=IdempotencyContextDTO(
                HttpMethod.POST,
                f"/v1/projects/{project_id.value}/model-connections",
                IdempotencyKey("migration-original"),
            ),
        )
    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings

    with pytest.raises(RuntimeError, match="Retained model connections"):
        command.downgrade(config, "0034_human_lifecycle")

    connection_id = result.connection.connection_id.value
    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        )
        assert await session.get(ModelConnectionRow, connection_id) is not None
        original = await session.get(
            ModelConnectionCreationResultRow, result.operation.operation_id.value
        )
        assert original is not None and original.model_connection_id == connection_id
        assignments = (
            await session.scalars(
                select(ModelConnectionActionGrantRow).where(
                    ModelConnectionActionGrantRow.model_connection_id == connection_id,
                )
            )
        ).all()
        assert {
            (grant.action, grant.recipient_principal_id, grant.can_grant) for grant in assignments
        } == {
            (action.value, seed.access.actor_principal_id.value, True)
            for action in ModelConnectionAction
        }
