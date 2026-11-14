from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import override
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    PROJECT_ID,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)
from tests.unit.access.application.services.test_model_connection_creation_service import (
    COMMAND as CREATE,
)
from tests.unit.access.application.services.test_model_connection_creation_service import (
    FACTS as CREATION_FACTS,
)

from inframeld_backend.access.application.commands.change_model_connection_credential_command import (
    ChangeModelConnectionCredentialCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.encrypted_provider_credential_dto import (
    EncryptedProviderCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_dto import (
    ModelConnectionCredentialDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_facts_dto import (
    ModelConnectionCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_credential_result_dto import (
    ModelConnectionCredentialResultDTO,
)
from inframeld_backend.access.application.protocols.model_connection_credential_repository import (
    ModelConnectionCredentialRepository,
)
from inframeld_backend.access.application.services.model_connection_credential_service import (
    ModelConnectionCredentialService,
)
from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.repositories.postgres_model_connection_credential_repository import (
    PostgresModelConnectionCredentialRepository,
)
from inframeld_backend.access.infrastructure.resources.pynacl_provider_credential_cipher import (
    PyNaClProviderCredentialCipher,
)
from inframeld_backend.access.infrastructure.settings.model_connection_destination_settings import (
    ModelConnectionDestinationSettings,
)
from inframeld_backend.access.infrastructure.settings.provider_credential_settings import (
    ProviderCredentialSettings,
)
from inframeld_backend.bootstrap.model_connection_composition import (
    open_model_connection_credentials,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.infrastructure.resources.database import Database

_CONNECTION = ModelConnectionId(UUID(int=700))
_EMPTY = ModelConnectionCredentialDTO(PROJECT_ID, _CONNECTION, None, 0, False, None)
_ORIGINAL = ModelConnectionCredentialDTO(
    PROJECT_ID, _CONNECTION, UUID(int=701), 1, True, datetime(2030, 1, 1, tzinfo=UTC)
)
_FACTS = ModelConnectionCredentialFactsDTO(
    CREATION_FACTS.organization_id, PROJECT_ID, CREATION_FACTS.action, CREATE.access, _EMPTY, None
)
_ROUTE = f"/v1/projects/{PROJECT_ID.value}/model-connections/{_CONNECTION.value}/credential"
_PUT = IdempotencyContextDTO(HttpMethod.PUT, _ROUTE, IdempotencyKey("credential-original"))
_DELETE = IdempotencyContextDTO(HttpMethod.DELETE, _ROUTE, IdempotencyKey("credential-remove"))
_COMMAND = ChangeModelConnectionCredentialCommand(
    PROJECT_ID, _CONNECTION, 0, ProviderCredentialValue("synthetic-key")
)


class _Repository(ModelConnectionCredentialRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = _FACTS
        self.saved: ModelConnectionCredentialDTO | None = None

    @override
    async def inspect(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        connection_id: ModelConnectionId,
        *,
        for_write: bool,
    ) -> ModelConnectionCredentialFactsDTO:
        self.events.append("write-authority" if for_write else "read-authority")
        return self.facts

    @override
    async def original(
        self,
        facts: ModelConnectionCredentialFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ModelConnectionCredentialResultDTO:
        self.events.append("original")
        return ModelConnectionCredentialResultDTO(_ORIGINAL, True, operation)

    @override
    async def save(
        self,
        facts: ModelConnectionCredentialFactsDTO,
        credential: ModelConnectionCredentialDTO,
        envelope: EncryptedProviderCredentialDTO | None,
        operation_id: OperationId,
    ) -> None:
        self.events.append("save")
        self.saved = credential

    @override
    async def save_result(
        self, facts: ModelConnectionCredentialFactsDTO, result: ModelConnectionCredentialResultDTO
    ) -> None:
        self.events.append("receipt")


@pytest.mark.asyncio
async def test_replay_recovers_original_before_live_revision_or_key_and_checks_current_grant(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    repository = _Repository(events)
    repository.facts = replace(_FACTS, credential=replace(_ORIGINAL, revision=8, present=False))
    idempotency = MockOperationIdempotency(events)
    service = ModelConnectionCredentialService(
        MockTransactions(events),
        repository,
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32)),
        PyNaClProviderCredentialCipher(tmp_path / "unreadable.key", None, "different"),
        ModelConnectionDestinationPolicy(),
    )
    replay = await service.change(ACCESS, _COMMAND, _PUT)
    assert replay == ModelConnectionCredentialResultDTO(_ORIGINAL, True, SAVED_RESULT)
    assert events == ["begin", "write-authority", "reserve", "original", "commit"]
    assert idempotency.lookup_authority is None
    original_fingerprint = idempotency.fingerprint
    await service.change(
        ACCESS, replace(_COMMAND, value=ProviderCredentialValue("other-synthetic-key")), _PUT
    )
    assert idempotency.fingerprint != original_fingerprint

    repository.facts = replace(_FACTS, action=replace(_FACTS.action, has_exact_action_grant=False))
    events.clear()
    with pytest.raises(AccessDeniedError):
        await service.change(ACCESS, _COMMAND, _PUT)
    assert events == ["begin", "write-authority", "rollback"]
    with pytest.raises(AccessDeniedError):
        await service.get(ACCESS, PROJECT_ID, _CONNECTION)


@pytest.mark.asyncio
async def test_fresh_stale_revision_precedes_root_access_and_absent_delete_is_explicit(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    repository = _Repository(events)
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION
    service = ModelConnectionCredentialService(
        MockTransactions(events),
        repository,
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32)),
        PyNaClProviderCredentialCipher(tmp_path / "unreadable.key", None, "different"),
        ModelConnectionDestinationPolicy(https_base_urls=frozenset({CREATE.access.base_url})),
    )
    with pytest.raises(StaleRevisionError):
        await service.change(ACCESS, replace(_COMMAND, expected_revision=1), _PUT)
    assert events == ["begin", "write-authority", "reserve", "rollback"]
    events.clear()
    with pytest.raises(DependencyUnavailableError, match="encryption key is unavailable"):
        await service.change(ACCESS, replace(_COMMAND, value=None), _DELETE)
    assert events == ["begin", "write-authority", "reserve", "rollback"]
    assert repository.saved is None
    assert await service.get(ACCESS, PROJECT_ID, _CONNECTION) == _EMPTY


class _DatabaseWithLateFailure(Database):
    def __init__(self, failure: Exception) -> None:
        self.failure = failure

    def _fail_commit(self, _: Session) -> None:
        raise self.failure

    @override
    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession]:
        engine = create_async_engine("postgresql+psycopg://", hide_parameters=True)
        try:
            async with AsyncSession(engine) as session:
                event.listen(session.sync_session, "before_commit", self._fail_commit)
                yield session
        finally:
            await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "database_failure",
    [
        OperationalError("controlled write", None, OSError("unavailable")),
        SqlAlchemyTimeoutError("controlled pool failure"),
    ],
)
async def test_connection_failure_from_credential_transaction_uses_safe_dependency_problem(
    database_failure: Exception,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        PostgresModelConnectionCredentialRepository, "inspect", AsyncMock(return_value=_FACTS)
    )
    database = _DatabaseWithLateFailure(database_failure)
    with pytest.raises(DependencyUnavailableError) as result:
        async with open_model_connection_credentials(
            database,
            RequestFingerprintKey(b"F" * 32),
            ModelConnectionDestinationSettings(),
            ProviderCredentialSettings(),
        ) as service:
            await service.get(ACCESS, PROJECT_ID, _CONNECTION)
    assert result.value.__cause__ is None
