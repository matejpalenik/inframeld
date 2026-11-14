"""Verify retained Processing Profile creation and creator grants in PostgreSQL."""

import asyncio
import json
import os
import tomllib
from dataclasses import replace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx2
import pytest
from pydantic import HttpUrl
from sqlalchemy import Integer, column, delete, func, select, table, update
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.ext.asyncio import AsyncSession
from tests.support.processing_profile_scenarios import profile_command, profile_context
from tests.support.project_creation_scenarios import create_project, seed_project_creator
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.settings.csrf_settings import CSRFSettings
from inframeld_backend.access.infrastructure.settings.kratos_settings import KratosSettings
from inframeld_backend.access.infrastructure.verifiers.kratos_browser_session_verifier import (
    KratosBrowserSessionVerifier,
)
from inframeld_backend.bootstrap.application_factory import create_app
from inframeld_backend.bootstrap.application_settings import get_settings
from inframeld_backend.indexing.application.dtos.processing_profile_creation_dto import (
    ProcessingProfileCreationDTO,
)
from inframeld_backend.indexing.application.services.processing_profile_creation_service import (
    ProcessingProfileCreationService,
)
from inframeld_backend.indexing.application.services.processing_profile_read_service import (
    ProcessingProfileReadService,
)
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_processing_profile_creation_repository import (
    PostgresProcessingProfileCreationRepository,
)
from inframeld_backend.indexing.infrastructure.repositories.postgres_processing_profile_read_repository import (
    PostgresProcessingProfileReadRepository,
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
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    IdempotencyKeyReusedError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.services.idempotency_service import IdempotencyService
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.sqlalchemy_transaction_manager import (
    SqlAlchemyTransactionManager,
)
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings
from inframeld_backend.shared.infrastructure.writers.postgres_operation_reservation_writer import (
    PostgresOperationReservationWriter,
)

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1",
        reason="Requires isolated PostgreSQL integration services",
    ),
]


def _creator(session: AsyncSession) -> ProcessingProfileCreationService:
    return ProcessingProfileCreationService(
        PostgresProcessingProfileCreationRepository(session),
        IdempotencyService(PostgresOperationReservationWriter(session)),
        RequestFingerprintService(RequestFingerprintKey(b"P" * 32)),
        transactions=SqlAlchemyTransactionManager(session),
    )


async def test_exact_view_filters_before_page_and_cursor_cannot_change_project(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project.project_id
    other = (await create_project(database, seed, name="other", key="other")).project.project_id
    command = profile_command(project)
    async with database.session() as session, session.begin():
        creator = _creator(session)
        created = [
            (
                await creator.create_in_transaction(
                    access=seed.access,
                    command=replace(command, name=ResourceName(name)),
                    context=profile_context(project, name),
                )
            ).profile
            for name in ("first", "second", "third")
        ]
        hidden, first, second = sorted(created, key=lambda profile: profile.id.value)
        await session.execute(
            delete(ProcessingProfileActionGrantRow).where(
                ProcessingProfileActionGrantRow.processing_profile_id == hidden.id.value,
                ProcessingProfileActionGrantRow.action == ProcessingProfileAction.VIEW.value,
            )
        )

    async with database.session() as session:
        reader = ProcessingProfileReadService(
            SqlAlchemyTransactionManager(session),
            PostgresProcessingProfileReadRepository(session, None),
        )
        page = await reader.list_profiles(seed.access, project, 1, None)
        assert page.items == (first,) and page.next_cursor is not None
        following = await reader.list_profiles(seed.access, project, 1, page.next_cursor)
        assert following.items == (second,) and following.next_cursor is None
        assert await reader.get(seed.access, project, first.id) == first
        with pytest.raises(ResourceNotFoundError):
            await reader.get(seed.access, project, hidden.id)
        with pytest.raises(ResourceNotFoundError):
            await reader.get(seed.access, other, first.id)
        with pytest.raises(InvalidInputError):
            await reader.list_profiles(seed.access, other, 1, page.next_cursor)


async def test_competing_create_waits_then_recovers_the_original(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project.project_id
    command = profile_command(project)
    context = profile_context(project, "original")

    async def compete() -> ProcessingProfileCreationDTO:
        async with database.session() as session, session.begin():
            return await _creator(session).create_in_transaction(
                access=seed.access, command=command, context=context
            )

    pid = column("pid", Integer)
    activity = table("pg_stat_activity", pid)
    async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
        async with database.session() as holder, holder.begin():
            original = await _creator(holder).create_in_transaction(
                access=seed.access, command=command, context=context
            )
            holder_pid = await holder.scalar(select(func.pg_backend_pid(type_=Integer)))
            assert holder_pid is not None
            competing = tasks.create_task(compete())
            async with asyncio.timeout(3):
                while not competing.done():
                    async with database.session() as observer:
                        blocked = await observer.scalar(
                            select(pid)
                            .select_from(activity)
                            .where(
                                func.pg_blocking_pids(pid, type_=ARRAY(Integer)).contains(
                                    [holder_pid]
                                )
                            )
                        )
                    if blocked is not None:
                        break
                    await asyncio.sleep(0.01)
                else:
                    pytest.fail("The competing create bypassed the original Project write.")
        replay = await competing

    assert replay == replace(original, operation=replace(original.operation, created=False))


async def test_creates_exact_grants_and_replays_without_restoring_revoked_authority(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    command = profile_command(project.project_id)
    context = profile_context(project.project_id, "original")
    async with database.session() as session:
        result = await _creator(session).create(
            access=seed.access, command=command, context=context
        )

    profile = result.profile.id.value
    actor = seed.access.actor_principal_id.value
    assert result.project_access_revision == 2
    assert result.profile.definition == command.definition
    async with database.session() as session, session.begin():
        grants = (await session.scalars(select(ProcessingProfileActionGrantRow))).all()
        assert {
            (
                grant.processing_profile_id,
                grant.recipient_principal_id,
                grant.action,
                grant.can_grant,
            )
            for grant in grants
        } == {(profile, actor, action.value, True) for action in ProcessingProfileAction}
        await session.execute(
            delete(ProcessingProfileActionGrantRow).where(
                ProcessingProfileActionGrantRow.processing_profile_id == profile,
                ProcessingProfileActionGrantRow.action == ProcessingProfileAction.VIEW.value,
            )
        )
        await session.execute(
            update(ProjectRow)
            .where(ProjectRow.id == project.project_id.value)
            .values(access_revision=3)
        )

    async with database.session() as session, session.begin():
        replay = await _creator(session).create_in_transaction(
            access=seed.access, command=command, context=context
        )
        assert replay == replace(result, operation=replace(result.operation, created=False))
        assert (await session.scalars(select(ProcessingProfileActionGrantRow.action))).all() == [
            ProcessingProfileAction.USE.value
        ]
        await session.execute(
            delete(ProjectActionGrantRow).where(
                ProjectActionGrantRow.project_id == project.project_id.value,
                ProjectActionGrantRow.recipient_principal_id == actor,
                ProjectActionGrantRow.action == ProjectAction.CREATE_PROCESSING_PROFILES.value,
            )
        )

    with pytest.raises(AccessDeniedError):
        async with database.session() as session, session.begin():
            await _creator(session).create_in_transaction(
                access=seed.access, command=command, context=context
            )


async def test_caller_rollback_leaves_no_creation_effects_or_original_reservation(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    command = profile_command(project.project_id)
    context = profile_context(project.project_id, "rolled-back")
    aborted = None
    with pytest.raises(RuntimeError, match="Later starter write failed"):
        async with database.session() as session, session.begin():
            aborted = await _creator(session).create_in_transaction(
                access=seed.access, command=command, context=context
            )
            raise RuntimeError("Later starter write failed")

    assert aborted is not None
    profile = aborted.profile.id.value
    operation = aborted.operation.operation_id.value
    async with database.session() as session, session.begin():
        assert await session.get(ProcessingProfileRow, profile) is None
        assert await session.get(ProcessingProfileCreationResultRow, operation) is None
        assert await session.get(IdempotencyReservationRow, operation) is None
        assert (
            await session.scalar(
                select(ProcessingProfileActionGrantRow.processing_profile_id).where(
                    ProcessingProfileActionGrantRow.processing_profile_id == profile
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.correlation_id == operation
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == 1
        )
        retried = await _creator(session).create_in_transaction(
            access=seed.access, command=command, context=context
        )
        assert retried.operation.created
        assert retried.operation.operation_id != aborted.operation.operation_id


async def test_duplicate_name_rolls_back_reservation_revision_and_side_effects(
    database: Database,
) -> None:
    seed = await seed_project_creator(database)
    project = (await create_project(database, seed)).project
    command = profile_command(project.project_id)
    context = profile_context(project.project_id, "original")
    async with database.session() as session, session.begin():
        original = await _creator(session).create_in_transaction(
            access=seed.access, command=command, context=context
        )

    with pytest.raises(ConflictError, match="Name is unavailable"):
        async with database.session() as session, session.begin():
            await _creator(session).create_in_transaction(
                access=seed.access,
                command=command,
                context=profile_context(project.project_id, "duplicate"),
            )

    changed = replace(command, definition=replace(command.definition, max_content_tokens=500))
    with pytest.raises(IdempotencyKeyReusedError):
        async with database.session() as session, session.begin():
            await _creator(session).create_in_transaction(
                access=seed.access, command=changed, context=context
            )

    operation = original.operation.operation_id.value
    profile = original.profile.id.value
    async with database.session() as session, session.begin():
        assert (await session.scalars(select(ProcessingProfileRow.id))).all() == [profile]
        assert (
            await session.scalars(select(ProcessingProfileCreationResultRow.operation_id))
        ).all() == [operation]
        assert len((await session.scalars(select(ProcessingProfileActionGrantRow))).all()) == 2
        audits = (
            await session.scalars(
                select(AccessAuditEventRow).where(
                    AccessAuditEventRow.event_type == "processing_profile_created"
                )
            )
        ).all()
        assert [(audit.correlation_id, audit.target_id) for audit in audits] == [
            (operation, profile)
        ]
        reservations = await session.scalars(
            select(IdempotencyReservationRow.operation_id).where(
                IdempotencyReservationRow.requested_route == context.requested_route
            )
        )
        assert reservations.all() == [operation]
        assert (
            await session.scalar(
                select(ProjectRow.access_revision).where(ProjectRow.id == project.project_id.value)
            )
            == 2
        )


async def test_documented_profile_copy_recreates_settings_and_only_destination_grants(
    database: Database, temporary_postgres_settings: DatabaseSettings
) -> None:
    seed = await seed_membership_project(database)
    source = seed.project.project_id
    destination = (
        await create_project(database, seed.actor, name="destination", key="destination")
    ).project.project_id
    await change_membership(database, seed, revision=seed.project.access_revision, key="source-bob")
    source_path = f"/v1/projects/{source.value}/processing-profiles"
    destination_path = f"/v1/projects/{destination.value}/processing-profiles"
    action = ProcessingProfileAction.VIEW.value
    definition_fields = {
        "doclingSlimVersion": "docling_slim_version",
        "doclingCoreVersion": "docling_core_version",
        "assetManifestSha256": "asset_manifest_sha256",
        "maxContentTokens": "max_content_tokens",
        "mergePeers": "merge_peers",
        "repeatTableHeader": "repeat_table_header",
        "ocrEnabled": "ocr_enabled",
    }
    documented = {
        "name": "support-chunks",
        "displayName": "Support chunks",
        "definition": {
            "doclingSlimVersion": "2.148.0",
            "doclingCoreVersion": "2.106.0",
            "assetManifestSha256": "7ea9f3c967a7bc66d2501e466334e7aef46a639e01a11376888321e0f0a51d0e",
            "maxContentTokens": 512,
            "mergePeers": True,
            "repeatTableHeader": True,
            "ocrEnabled": False,
        },
    }
    settings = get_settings().model_copy(
        update={
            "database": temporary_postgres_settings,
            "kratos": KratosSettings(
                public_url=HttpUrl("http://kratos.test"),
                admin_url=HttpUrl("http://kratos-admin.test"),
                authority=seed.actor.binding.identity.authority,
            ),
            "csrf": CSRFSettings(trusted_origins=(HttpUrl("https://account.test"),)),
        }
    )
    verifier = AsyncMock(return_value=seed.actor.binding.identity)
    headers = {"Origin": "https://account.test", "X-Inframeld-CSRF": "1"}
    with patch.object(KratosBrowserSessionVerifier, "verify", verifier):
        app = create_app(settings)
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app),
                base_url="https://api.test",
                cookies={"ory_kratos_session": "controlled-alice"},
                headers=headers,
            ) as client,
        ):
            response = await client.post(
                source_path, json=documented, headers={"Idempotency-Key": "source-definition"}
            )
            assert response.status_code == 201
            original = response.json()
            source_id = original["profile"]["processingProfileId"]
            granted = await client.put(
                f"/v1/processing-profiles/{source_id}/grants/{seed.bob_id.value}/{action}",
                headers={"Idempotency-Key": "source-view-bob"},
                json={
                    "expectedAccessRevision": original["projectAccessRevision"],
                    "canGrant": False,
                },
            )
            assert granted.status_code == 201
            response = await client.get(f"{source_path}/{source_id}")
            assert response.status_code == 200
            stored = response.json()
            spec = "\n".join(
                f"{toml_key} = {json.dumps(stored['definition'][api_key])}"
                for api_key, toml_key in definition_fields.items()
            )
            portable = tomllib.loads(
                'schema_version = 1\nkind = "processing-profile"\n\n[metadata]\n'
                + f"name = {json.dumps(stored['name'])}\n"
                + f"display_name = {json.dumps(stored['displayName'])}\n\n[spec]\n{spec}\n"
            )
            assert portable["schema_version"] == 1 and portable["kind"] == "processing-profile"
            request = {
                "name": portable["metadata"]["name"],
                "displayName": portable["metadata"]["display_name"],
                "definition": {
                    key: portable["spec"][portable_key]
                    for key, portable_key in definition_fields.items()
                },
            }
            assert request == documented
            listing = await client.get(destination_path)
            assert listing.status_code == 200 and listing.json() == {
                "items": [],
                "nextCursor": None,
            }
            copied = await client.post(
                destination_path,
                json=request,
                headers={"Idempotency-Key": "destination-definition"},
            )
            assert copied.status_code == 201
            result = copied.json()
            copied_id = result["profile"]["processingProfileId"]
            assert copied_id != source_id
            assert result["initialGrants"] == [
                {
                    "target": {"kind": "processing-profile", "processingProfileId": copied_id},
                    "actionId": item.value,
                    "canGrant": True,
                }
                for item in ProcessingProfileAction
            ]
            reread = await client.get(f"{destination_path}/{copied_id}")
            assert reread.status_code == 200
            assert reread.json() == {
                "projectId": str(destination.value),
                "processingProfileId": copied_id,
                **documented,
            }
    async with database.session() as session:
        for identifier, expected in (
            (
                UUID(source_id),
                {
                    (seed.actor.access.actor_principal_id.value, item.value, True)
                    for item in ProcessingProfileAction
                }
                | {(seed.bob_id.value, action, False)},
            ),
            (
                UUID(copied_id),
                {
                    (seed.actor.access.actor_principal_id.value, item.value, True)
                    for item in ProcessingProfileAction
                },
            ),
        ):
            rows = await session.execute(
                select(
                    ProcessingProfileActionGrantRow.recipient_principal_id,
                    ProcessingProfileActionGrantRow.action,
                    ProcessingProfileActionGrantRow.can_grant,
                ).where(ProcessingProfileActionGrantRow.processing_profile_id == identifier)
            )
            assert set(rows.tuples()) == expected
