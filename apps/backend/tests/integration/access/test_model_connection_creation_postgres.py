"""Qualify exact Project authority, atomic creator grants, and original replay."""

import os
from dataclasses import replace

import pytest
from sqlalchemy import delete, select
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
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.bootstrap.model_connection_composition import (
    open_model_connection_creation,
    open_model_connection_read,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    ResourceNotFoundError,
)
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
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


async def test_atomic_creation_filters_current_reads_and_keeps_original_assignments(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    project_id = project.project_id
    url = "https://models.example.test/v1"
    request = CreateModelConnectionCommand(
        project_id,
        ResourceName("company-gateway"),
        SubmittedDisplayName("Company gateway"),
        ModelConnectionAccessDTO(
            ModelConnectionProvider.OPENAI_COMPATIBLE,
            url,
            None,
            ModelConnectionAuthentication.API_KEY,
        ),
    )
    context = IdempotencyContextDTO(
        HttpMethod.POST,
        f"/v1/projects/{project_id.value}/model-connections",
        IdempotencyKey("original"),
    )
    fingerprints = RequestFingerprintService(RequestFingerprintKey(b"M" * 32))
    destinations = ModelConnectionDestinationSettings(https_base_urls=frozenset({url}))
    async with open_model_connection_creation(database, fingerprints, destinations) as creator:
        original = await creator.create(access=seed.access, command=request, context=context)
    connection_id = original.connection.connection_id
    assert original.project_access_revision == 2
    assert original.initial_actions == tuple(ModelConnectionAction)

    async with open_model_connection_creation(database, fingerprints, destinations) as creator:
        with pytest.raises(ConflictError):
            await creator.create(
                access=seed.access,
                command=request,
                context=replace(context, key=IdempotencyKey("conflicting-name")),
            )
    async with database.session() as session, session.begin():
        rows = (await session.scalars(select(ModelConnectionRow))).all()
        assert [row.id for row in rows] == [connection_id.value]
        assignments = (
            await session.scalars(
                select(ModelConnectionActionGrantRow).where(
                    ModelConnectionActionGrantRow.model_connection_id == connection_id.value,
                )
            )
        ).all()
        assert {(row.action, row.recipient_principal_id, row.can_grant) for row in assignments} == {
            (action.value, seed.access.actor_principal_id.value, True)
            for action in ModelConnectionAction
        }
        audits = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.event_type == "model_connection_created"
                )
            )
        ).all()
        assert [row.correlation_id for row in audits] == [original.operation.operation_id.value]
        reservations = (
            await session.scalars(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.requested_route == context.requested_route,
                )
            )
        ).all()
        assert reservations == [original.operation.operation_id.value]

    async with open_model_connection_read(database, None) as reader:
        assert await reader.get(seed.access, project_id, connection_id) == original.connection
        assert (await reader.list_connections(seed.access, project_id, 25, None)).items == (
            original.connection,
        )
        await reader.list_usage(seed.access, project_id, connection_id, 25, None)

    async with database.session() as session, session.begin():
        await session.execute(
            delete(ModelConnectionActionGrantRow).where(
                ModelConnectionActionGrantRow.model_connection_id == connection_id.value,
                ModelConnectionActionGrantRow.action
                == ModelConnectionAction.VIEW_CONFIGURATION.value,
            )
        )
    async with open_model_connection_read(database, None) as reader:
        assert (await reader.list_connections(seed.access, project_id, 25, None)).items == ()
        with pytest.raises(ResourceNotFoundError):
            await reader.list_usage(seed.access, project_id, connection_id, 25, None)
    async with open_model_connection_creation(
        database, fingerprints, ModelConnectionDestinationSettings()
    ) as creator:
        replay = await creator.create(access=seed.access, command=request, context=context)
    assert replay == replace(original, operation=replace(original.operation, created=False))

    async with database.session() as session, session.begin():
        view = await session.get(
            ModelConnectionActionGrantRow,
            (
                project_id.value,
                connection_id.value,
                seed.access.actor_principal_id.value,
                ModelConnectionAction.VIEW_CONFIGURATION.value,
            ),
        )
        assert view is None
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == project_id.value,
                ProjectActionGrantRow.recipient_principal_id
                == seed.access.actor_principal_id.value,
                ProjectActionGrantRow.action == ProjectAction.CREATE_MODEL_CONNECTIONS.value,
            )
        )
    async with open_model_connection_creation(database, fingerprints, destinations) as creator:
        with pytest.raises(AccessDeniedError):
            await creator.create(access=seed.access, command=request, context=context)
