"""Qualify the protected credential slot through real contention and transaction rollback."""

import asyncio
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from hashlib import sha256
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from tests.support.project_membership_postgres_scenarios import (
    change_membership,
    seed_membership_project,
)

from inframeld_backend.access.application.commands.change_model_connection_credential_command import (
    ChangeModelConnectionCredentialCommand,
)
from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_result_dto import (
    ModelConnectionCredentialResultDTO,
)
from inframeld_backend.access.application.dtos.provider_credential_binding_dto import (
    ProviderCredentialBindingDTO,
)
from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.infrastructure.resources.pynacl_provider_credential_cipher import (
    PyNaClProviderCredentialCipher,
)
from inframeld_backend.access.infrastructure.rows.access_audit_event_row import AccessAuditEventRow
from inframeld_backend.access.infrastructure.rows.model_connection_credential_result_row import (
    ModelConnectionCredentialResultRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_credential_row import (
    ModelConnectionCredentialRow,
)
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.access.infrastructure.settings.provider_credential_settings import (
    ProviderCredentialSettings,
)
from inframeld_backend.bootstrap.model_connection_composition import (
    open_model_connection_creation,
    open_model_connection_credentials,
    open_model_connection_grant_change,
    open_model_connection_read,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    IdempotencyKeyReusedError,
    StaleRevisionError,
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
from inframeld_backend.shared.infrastructure.migrations.migration_runner import (
    ALEMBIC_CONFIG_PATH,
    SUPPORTED_SCHEMA_REVISION,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.alembic_version_row import AlembicVersionRow
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)
from inframeld_backend.shared.infrastructure.settings.database_settings import DatabaseSettings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        os.getenv("INFRAMELD_RUN_DB_INTEGRATION") != "1", reason="Requires isolated PostgreSQL"
    ),
]

_URL = "https://models.example.test/v1"
_DESTINATIONS = ModelConnectionDestinationSettings(https_base_urls=frozenset({_URL}))
_FINGERPRINT_KEY = RequestFingerprintKey(b"F" * 32)
_FINGERPRINTS = RequestFingerprintService(_FINGERPRINT_KEY)
_ROOT = bytes(range(32))
_ROOT_ID = sha256(_ROOT).hexdigest()


def _provider_settings(path: Path, material: bytes = _ROOT) -> ProviderCredentialSettings:
    path.write_bytes(material)
    path.chmod(0o600)
    return ProviderCredentialSettings(key_file=path, expected_key_id=_ROOT_ID)


async def test_credential_rotation_replay_removal_and_rollback_use_live_exact_management(
    database: Database,
    temporary_postgres_settings: DatabaseSettings,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed = await seed_membership_project(database)
    actor, project = seed.actor, seed.project
    project_id = project.project_id
    await change_membership(database, seed, revision=project.access_revision, key="join-bob")
    create_input = CreateModelConnectionCommand(
        project_id,
        ResourceName("credential-gateway"),
        SubmittedDisplayName("Credential gateway"),
        ModelConnectionAccessDTO(
            ModelConnectionProvider.OPENAI_COMPATIBLE,
            _URL,
            None,
            ModelConnectionAuthentication.API_KEY,
        ),
    )
    collection = f"/v1/projects/{project_id.value}/model-connections"
    create_context = IdempotencyContextDTO(HttpMethod.POST, collection, IdempotencyKey("create"))
    async with open_model_connection_creation(database, _FINGERPRINTS, _DESTINATIONS) as creator:
        created = await creator.create(
            access=actor.access, command=create_input, context=create_context
        )
    connection = created.connection.connection_id
    route = f"{collection}/{connection.value}/credential"
    put = IdempotencyContextDTO(HttpMethod.PUT, route, IdempotencyKey("save-key"))
    first = ChangeModelConnectionCredentialCommand(
        project_id, connection, 0, ProviderCredentialValue("original-secret-fixture")
    )
    wrong_key = _provider_settings(tmp_path / "wrong.key", bytes(reversed(_ROOT)))
    async with open_model_connection_credentials(
        database, _FINGERPRINT_KEY, _DESTINATIONS, wrong_key
    ) as credentials:
        never_written = await credentials.get(actor.access, project_id, connection)
        assert (never_written.revision, never_written.present, never_written.credential_id) == (
            0,
            False,
            None,
        )
        with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
            await credentials.change(actor.access, first, put)

    settings = _provider_settings(tmp_path / "root.key")
    cipher = PyNaClProviderCredentialCipher(
        settings.key_file, settings.expected_key_id, sha256(_FINGERPRINT_KEY.value).hexdigest()
    )
    commit_attempted = False

    def fail_commit(_: Session) -> None:
        nonlocal commit_attempted
        commit_attempted = True
        raise OperationalError(None, None, OSError("Controlled commit connection failure."))

    original_session = database.session

    @asynccontextmanager
    async def interrupt_commit() -> AsyncGenerator[AsyncSession]:
        async with original_session() as session:
            event.listen(session.sync_session, "before_commit", fail_commit)
            yield session

    with monkeypatch.context() as patched:
        patched.setattr(database, "session", interrupt_commit)
        with pytest.raises(DependencyUnavailableError):
            async with open_model_connection_credentials(
                database, _FINGERPRINT_KEY, _DESTINATIONS, settings
            ) as credentials:
                await credentials.change(actor.access, first, put)
    assert commit_attempted
    async with database.session() as session:
        assert (
            await session.scalar(select(func.count()).select_from(ModelConnectionCredentialRow))
            == 0
        )
        assert (
            await session.scalar(
                select(func.count()).select_from(ModelConnectionCredentialResultRow)
            )
            == 0
        )
        assert (
            await session.scalar(
                select(IdempotencyReservationRow.operation_id).where(
                    IdempotencyReservationRow.requested_route == route
                )
            )
            is None
        )
        assert (
            await session.scalar(
                select(AccessAuditEventRow.id).where(
                    AccessAuditEventRow.event_type == "model_connection_credential_changed"
                )
            )
            is None
        )

    async with open_model_connection_credentials(
        database, _FINGERPRINT_KEY, _DESTINATIONS, settings
    ) as credentials:
        saved = await credentials.change(actor.access, first, put)
    assert saved.credential.present and saved.credential.revision == 1
    assert saved.operation.created and saved.changed
    credential_id = saved.credential.credential_id
    assert credential_id is not None
    async with database.session() as session:
        row = await session.get(ModelConnectionCredentialRow, credential_id)
        assert (
            row is not None
            and row.format_version is not None
            and row.algorithm is not None
            and row.key_id is not None
            and row.ciphertext is not None
        )
        assert first.value is not None and first.value.value.encode() not in row.ciphertext
        assert (
            cipher.decrypt(
                EncryptedProviderCredentialDTO(
                    row.format_version, row.algorithm, row.key_id, row.ciphertext
                ),
                ProviderCredentialBindingDTO(
                    actor.organization_id, project_id, connection, credential_id, 1
                ),
            )
            == first.value
        )

    manage, view = ModelConnectionAction.MANAGE, ModelConnectionAction.VIEW_CONFIGURATION

    async def set_bob(action: ModelConnectionAction, revision: int, level: bool | None):
        method = HttpMethod.DELETE if level is None else HttpMethod.PUT
        grant_context = IdempotencyContextDTO(
            method,
            f"/v1/model-connections/{connection.value}/grants/{seed.bob_id.value}/{action.value}",
            IdempotencyKey(f"{method.value}-{action.value}"),
        )
        async with open_model_connection_grant_change(database, _FINGERPRINTS) as changer:
            return await changer.change(
                actor.access,
                ChangeModelConnectionGrantCommand(connection, seed.bob_id, action, revision, level),
                grant_context,
            )

    view_grant = await set_bob(view, created.project_access_revision, False)
    async with open_model_connection_read(database, None) as reader:
        summary = await reader.get(seed.bob_access, project_id, connection)
        assert (summary.credential_present, summary.credential_revision) == (True, 1)
        assert (await reader.list_connections(seed.bob_access, project_id, 10, None)).items == (
            summary,
        )
    async with open_model_connection_credentials(
        database, _FINGERPRINT_KEY, _DESTINATIONS, settings
    ) as credentials:
        with pytest.raises(AccessDeniedError):
            await credentials.get(seed.bob_access, project_id, connection)
    manage_grant = await set_bob(manage, view_grant.access_revision, False)

    entered = asyncio.Barrier(2)

    async def rotate(
        access: AccessContextDTO, label: str
    ) -> ModelConnectionCredentialResultDTO | StaleRevisionError:
        async with open_model_connection_credentials(
            database, _FINGERPRINT_KEY, _DESTINATIONS, settings
        ) as credentials:
            await entered.wait()
            try:
                return await credentials.change(
                    access,
                    replace(first, expected_revision=1, value=ProviderCredentialValue(label)),
                    replace(put, key=IdempotencyKey(label)),
                )
            except StaleRevisionError as failure:
                return failure

    alice, bob = await asyncio.gather(
        rotate(actor.access, "alice-rotated-fixture"),
        rotate(seed.bob_access, "bob-rotated-fixture"),
    )
    winners = [
        result for result in (alice, bob) if isinstance(result, ModelConnectionCredentialResultDTO)
    ]
    assert sum(isinstance(result, StaleRevisionError) for result in (alice, bob)) == 1
    assert len(winners) == 1 and winners[0].credential.revision == 2
    assert winners[0].credential.credential_id == credential_id

    async with open_model_connection_credentials(
        database, _FINGERPRINT_KEY, ModelConnectionDestinationSettings(), wrong_key
    ) as credentials:
        replay = await credentials.change(actor.access, first, put)
        assert replay == replace(saved, operation=replace(saved.operation, created=False))
        with pytest.raises(IdempotencyKeyReusedError):
            await credentials.change(
                actor.access, replace(first, value=ProviderCredentialValue("changed-fixture")), put
            )
        assert (await credentials.get(seed.bob_access, project_id, connection)).revision == 2

    await set_bob(manage, manage_grant.access_revision, None)
    remove = replace(first, expected_revision=2, value=None)
    remove_context = IdempotencyContextDTO(HttpMethod.DELETE, route, IdempotencyKey("remove"))
    async with open_model_connection_credentials(
        database, _FINGERPRINT_KEY, ModelConnectionDestinationSettings(), settings
    ) as credentials:
        with pytest.raises(AccessDeniedError):
            await credentials.change(seed.bob_access, remove, remove_context)
        removed = await credentials.change(actor.access, remove, remove_context)
        assert removed.credential.credential_id == credential_id
        assert (removed.credential.present, removed.credential.revision) == (False, 3)
        unchanged = await credentials.change(
            actor.access,
            replace(remove, expected_revision=3),
            replace(remove_context, key=IdempotencyKey("already-absent")),
        )
        assert unchanged.credential == removed.credential and not unchanged.changed

    async with open_model_connection_credentials(
        database, _FINGERPRINT_KEY, ModelConnectionDestinationSettings(), wrong_key
    ) as credentials:
        repeated_remove = await credentials.change(actor.access, remove, remove_context)
        assert repeated_remove == replace(
            removed, operation=replace(removed.operation, created=False)
        )
        assert (await credentials.get(actor.access, project_id, connection)) == removed.credential

    async with open_model_connection_creation(database, _FINGERPRINTS, _DESTINATIONS) as creator:
        creation_replay = await creator.create(
            access=actor.access, command=create_input, context=create_context
        )
        assert creation_replay.connection == created.connection
        assert (
            creation_replay.connection.credential_present,
            creation_replay.connection.credential_revision,
        ) == (False, 0)

    config = Config(str(ALEMBIC_CONFIG_PATH))
    config.attributes["database_settings"] = temporary_postgres_settings
    with pytest.raises(RuntimeError, match="Retained model connection credentials"):
        command.downgrade(config, "0035_model_connections")

    async with database.session() as session:
        assert (
            await session.scalar(select(AlembicVersionRow.version_num)) == SUPPORTED_SCHEMA_REVISION
        )
        row = await session.get(ModelConnectionCredentialRow, credential_id)
        assert row is not None and row.revision == 3
        assert (row.format_version, row.algorithm, row.key_id, row.ciphertext) == (
            None,
            None,
            None,
            None,
        )
        audits = (
            await session.scalars(
                select(AccessAuditEventRow)
                .where(AccessAuditEventRow.event_type == "model_connection_credential_changed")
                .order_by(AccessAuditEventRow.occurred_at)
            )
        ).all()
        assert [item.after_values for item in audits] == [
            {"revision": 1, "present": True},
            {"revision": 2, "present": True},
            {"revision": 3, "present": False},
        ]
        assert (
            await session.scalar(
                select(func.count()).select_from(ModelConnectionCredentialResultRow)
            )
            == 4
        )
