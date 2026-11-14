from dataclasses import replace
from typing import override

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.create_model_connection_command import (
    CreateModelConnectionCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_access_dto import (
    ModelConnectionAccessDTO,
)
from inframeld_backend.access.application.dtos.model_connection_creation_dto import (
    ModelConnectionCreationDTO,
)
from inframeld_backend.access.application.dtos.model_connection_creation_facts_dto import (
    ModelConnectionCreationFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_dto import ModelConnectionDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.model_connection_creation_repository import (
    ModelConnectionCreationRepository,
)
from inframeld_backend.access.application.services.model_connection_creation_service import (
    ModelConnectionCreationService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    InvalidInputError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)

COMMAND = CreateModelConnectionCommand(
    PROJECT_ID,
    ResourceName("company-gateway"),
    SubmittedDisplayName("Company gateway"),
    ModelConnectionAccessDTO(
        ModelConnectionProvider.OPENAI_COMPATIBLE,
        "https://models.example.test/v1",
        None,
        ModelConnectionAuthentication.API_KEY,
    ),
)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.POST,
    f"/v1/projects/{PROJECT_ID.value}/model-connections",
    IdempotencyKey("original"),
)
FACTS = ModelConnectionCreationFactsDTO(
    ORGANIZATION_ID,
    PROJECT_ID,
    7,
    ProjectActionFactsDTO(
        Principal(
            ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
        ),
        False,
        HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
        ProjectStatus.ACTIVE,
        True,
        True,
    ),
)


class MockCreationRepository(ModelConnectionCreationRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = FACTS
        self.saved: ModelConnectionDTO | None = None
        self.actions: tuple[ModelConnectionAction, ...] = ()

    @override
    async def lock_for_creation(
        self, access: AccessContextDTO, project_id: ProjectId
    ) -> ModelConnectionCreationFactsDTO:
        self.events.append("authority")
        return self.facts

    @override
    async def original(
        self,
        access: AccessContextDTO,
        facts: ModelConnectionCreationFactsDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ModelConnectionCreationDTO:
        self.events.append("original")
        assert self.saved is not None
        return ModelConnectionCreationDTO(self.saved, operation, 8, self.actions)

    @override
    async def save(
        self,
        access: AccessContextDTO,
        facts: ModelConnectionCreationFactsDTO,
        operation_id: OperationId,
        connection: ModelConnectionDTO,
        initial_actions: tuple[ModelConnectionAction, ...],
    ) -> None:
        self.events.append("save")
        self.saved, self.actions = connection, initial_actions


@pytest.mark.asyncio
async def test_creation_and_replay_preserve_the_four_original_assignments() -> None:
    events: list[str] = []
    repository = MockCreationRepository(events)
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION
    service = ModelConnectionCreationService(
        MockTransactions(events),
        repository,
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32)),
        ModelConnectionDestinationPolicy(https_base_urls=frozenset({COMMAND.access.base_url})),
    )

    result = await service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result.initial_actions == tuple(ModelConnectionAction)
    assert result.project_access_revision == 8
    assert result.connection.credential_present is False
    assert (
        result.connection.credential_revision,
        result.connection.connection_access_revision,
    ) == (0, 0)
    assert events == ["begin", "authority", "reserve", "save", "complete", "commit"]

    events.clear()
    idempotency.result = replace(result.operation, created=False)
    repository.facts = replace(FACTS, access_revision=13)
    replay = await service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert replay == replace(result, operation=idempotency.result)
    assert events == ["begin", "authority", "reserve", "original", "commit"]


@pytest.mark.asyncio
async def test_denied_authority_never_replays_and_unapproved_destination_never_saves() -> None:
    events: list[str] = []
    repository = MockCreationRepository(events)
    idempotency = MockOperationIdempotency(events)
    service = ModelConnectionCreationService(
        MockTransactions(events),
        repository,
        idempotency,
        RequestFingerprintService(RequestFingerprintKey(b"F" * 32)),
        ModelConnectionDestinationPolicy(),
    )
    repository.facts = replace(FACTS, action=replace(FACTS.action, has_exact_action_grant=False))
    with pytest.raises(AccessDeniedError):
        await service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert events == ["begin", "authority", "rollback"]

    events.clear()
    repository.facts = FACTS
    idempotency.result = NEW_RESERVATION
    with pytest.raises(InvalidInputError):
        await service.create(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert "save" not in events and events[-1] == "rollback"
