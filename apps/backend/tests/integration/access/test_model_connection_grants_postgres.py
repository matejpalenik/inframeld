"""Protect exact model grants across competing revisions, departure, and original recovery."""

import asyncio
import os
from dataclasses import replace

import pytest
from sqlalchemy import select
from tests.support.project_creation_scenarios import create_project
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.queries.list_project_grant_recipients_query import (
    ListProjectGrantRecipientsQuery,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.bootstrap.grant_recipients_composition import open_project_grant_recipients
from inframeld_backend.bootstrap.model_connection_composition import (
    open_model_connection_creation,
    open_model_connection_grant_change,
    open_model_connection_grant_read,
    open_model_connection_read,
)
from inframeld_backend.bootstrap.original_operation_lookup_composition import (
    open_original_operation_lookup,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.queries.lookup_original_operation_query import (
    LookupOriginalOperationQuery,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1", reason="Requires isolated PostgreSQL"
    ),
]


async def test_grant_handover_replay_and_membership_departure_use_current_exact_scope(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    actor, project = seed.actor, seed.project
    project_id = project.project_id
    unrelated = (
        await create_project(
            database,
            actor,
            name="unrelated",
            key="other-project",
        )
    ).project.project_id
    joined = await change_membership(database, seed, revision=project.access_revision, key="join")
    url = "https://models.example.test/v1"
    fingerprints = RequestFingerprintService(RequestFingerprintKey(b"M" * 32))
    async with open_model_connection_creation(
        database,
        fingerprints,
        ModelConnectionDestinationSettings(https_base_urls=frozenset({url})),
    ) as creator:
        original = await creator.create(
            access=actor.access,
            command=CreateModelConnectionCommand(
                project_id,
                ResourceName("member-gateway"),
                SubmittedDisplayName("Member gateway"),
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
                IdempotencyKey("create"),
            ),
        )
    connection = original.connection.connection_id
    assert original.project_access_revision == joined.access_revision + 1
    action = ModelConnectionAction.VIEW_CONFIGURATION
    target = ModelConnectionGrantTargetDTO(project_id, connection)
    query = ListProjectGrantRecipientsQuery(project_id, target, ActionId(action.value))
    async with open_project_grant_recipients(database) as directory:
        assert {
            item.principal_id
            for item in (await directory.list_recipients(access=actor.access, query=query)).items
        } == {
            actor.access.actor_principal_id,
            seed.bob_id,
        }
        with pytest.raises(ResourceNotFoundError):
            await directory.list_recipients(
                access=actor.access,
                query=replace(
                    query, project_id=unrelated, target=replace(target, project_id=unrelated)
                ),
            )

    route = f"/v1/model-connections/{connection.value}/grants/{seed.bob_id.value}/{action.value}"
    context = IdempotencyContextDTO(HttpMethod.PUT, route, IdempotencyKey("grant-bob"))
    command = ChangeModelConnectionGrantCommand(
        connection, seed.bob_id, action, original.project_access_revision, False
    )
    async with open_model_connection_grant_change(database, fingerprints) as changer:
        grant = await changer.change(actor.access, command, context)
    assert (
        grant.status_code == 201
        and grant.changed
        and grant.access_revision == original.project_access_revision + 1
    )

    async with open_model_connection_grant_change(database, fingerprints) as changer:
        with pytest.raises(StaleRevisionError):
            await changer.change(
                actor.access, command, replace(context, key=IdempotencyKey("stale"))
            )
    async with open_model_connection_grant_change(database, fingerprints) as changer:
        noop = await changer.change(
            actor.access,
            replace(command, expected_access_revision=grant.access_revision),
            replace(context, key=IdempotencyKey("unchanged")),
        )
    assert (
        noop.status_code == 200
        and not noop.changed
        and noop.access_revision == grant.access_revision
    )

    async with open_model_connection_grant_read(database) as reader:
        page = await reader.list_grants(actor.access, connection, action, 1, None)
        assert len(page.items) == 1 and page.next_cursor is not None
        following = await reader.list_grants(actor.access, connection, action, 1, page.next_cursor)
        assert {item.recipient_id for item in (*page.items, *following.items)} == {
            actor.access.actor_principal_id,
            seed.bob_id,
        }
        assert following.next_cursor is None
        with pytest.raises(InvalidInputError):
            await reader.list_grants(
                actor.access, connection, ModelConnectionAction.USE, 1, page.next_cursor
            )
        with pytest.raises(AccessDeniedError):
            await reader.list_grants(seed.bob_access, connection, action, 25, None)
    async with open_model_connection_read(database, None) as reader:
        assert await reader.get(seed.bob_access, project_id, connection) == original.connection

    lookup = LookupOriginalOperationQuery(
        actor.binding.installation_id,
        actor.organization_id,
        project_id,
        HttpMethod.PUT,
        route,
        context.key,
        OperationLookupAuthority(
            OperationLookupAuthorityFamily.MODEL_CONNECTION_GRANT_READ, ActionId(action.value)
        ),
    )
    async with open_original_operation_lookup(database) as operations:
        observed = await operations.lookup(access=actor.access, query=lookup)
        assert observed == replace(grant.operation, created=False)
        with pytest.raises(ResourceNotFoundError):
            await operations.lookup(
                access=actor.access, query=replace(lookup, project_id=unrelated)
            )
        with pytest.raises(InvalidInputError):
            await operations.lookup(
                access=actor.access,
                query=replace(
                    lookup,
                    expected_authority=OperationLookupAuthority(
                        OperationLookupAuthorityFamily.PROJECT_ACTION_USE,
                        ActionId("create-model-connections"),
                    ),
                ),
            )

    own = actor.access.actor_principal_id
    own_route = f"/v1/model-connections/{connection.value}/grants/{own.value}/{action.value}"
    own_context = IdempotencyContextDTO(
        HttpMethod.DELETE, own_route, IdempotencyKey("retire-creator")
    )
    own_command = replace(
        command, recipient_id=own, expected_access_revision=grant.access_revision, can_grant=None
    )
    async with open_model_connection_grant_change(database, fingerprints) as changer:
        with pytest.raises(ConflictError, match="eligible human grantor"):
            await changer.change(actor.access, own_command, own_context)
    async with open_model_connection_grant_change(database, fingerprints) as changer:
        delegated = await changer.change(
            actor.access,
            replace(command, expected_access_revision=grant.access_revision, can_grant=True),
            replace(context, key=IdempotencyKey("handover")),
        )
    async with open_model_connection_grant_change(database, fingerprints) as changer:
        replay = await changer.change(actor.access, command, context)
        assert replay == replace(grant, operation=replace(grant.operation, created=False))
    async with open_model_connection_grant_change(database, fingerprints) as changer:
        removal = await changer.change(
            actor.access,
            replace(own_command, expected_access_revision=delegated.access_revision),
            own_context,
        )
    async with open_model_connection_grant_change(database, fingerprints) as changer:
        with pytest.raises(AccessDeniedError):
            await changer.change(actor.access, command, context)
    async with open_original_operation_lookup(database) as operations:
        with pytest.raises(AccessDeniedError):
            await operations.lookup(access=actor.access, query=lookup)

    with pytest.raises(ConflictError):
        await change_membership(
            database, seed, revision=removal.access_revision, key="blocked-departure", remove=True
        )
    with pytest.raises(ResourceNotFoundError):
        async with open_model_connection_read(database, None) as reader:
            await reader.get(actor.access, project_id, connection)

    async with open_model_connection_grant_change(database, fingerprints) as changer:
        transferred = await changer.change(
            seed.bob_access,
            replace(own_command, expected_access_revision=removal.access_revision, can_grant=True),
            IdempotencyContextDTO(HttpMethod.PUT, own_route, IdempotencyKey("replacement-grantor")),
        )
    left = await change_membership(
        database, seed, revision=transferred.access_revision, key="leave", remove=True
    )
    await change_membership(database, seed, revision=left.access_revision, key="rejoin")
    async with open_model_connection_read(database, None) as reader:
        with pytest.raises(ResourceNotFoundError):
            await reader.get(seed.bob_access, project_id, connection)
    async with database.session() as session:
        assert (
            await session.scalar(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.correlation_id == noop.operation.operation_id.value,
                )
            )
            is None
        )


async def test_nonmember_grant_read_does_not_wait_for_the_guessed_project_lock(
    database: Database,
) -> None:
    seed = await seed_membership_project(database)
    project_id = seed.project.project_id
    url = "https://models.example.test/v1"
    async with open_model_connection_creation(
        database,
        RequestFingerprintService(RequestFingerprintKey(b"M" * 32)),
        ModelConnectionDestinationSettings(https_base_urls=frozenset({url})),
    ) as creator:
        result = await creator.create(
            access=seed.actor.access,
            command=CreateModelConnectionCommand(
                project_id,
                ResourceName("private-model"),
                SubmittedDisplayName("Private model"),
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
                IdempotencyKey("create-private"),
            ),
        )
    async with database.session() as blocker, blocker.begin():
        assert (
            await blocker.scalar(
                select(ProjectRow.id).where(ProjectRow.id == project_id.value).with_for_update()
            )
            == project_id.value
        )
        async with open_model_connection_grant_read(database) as reader:
            async with asyncio.timeout(1):
                with pytest.raises(ResourceNotFoundError):
                    await reader.list_grants(
                        seed.bob_access,
                        result.connection.connection_id,
                        ModelConnectionAction.USE,
                        25,
                        None,
                    )
