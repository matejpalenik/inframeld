from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    MockOperationIdempotency,
    MockTransactions,
)
from tests.unit.access.application.services.test_model_connection_creation_service import FACTS

from inframeld_backend.access.application.commands.change_model_connection_grant_command import (
    ChangeModelConnectionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.model_connection_grant_facts_dto import (
    ModelConnectionGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_result_dto import (
    ModelConnectionGrantResultDTO,
)
from inframeld_backend.access.application.protocols.model_connection_grant_repository import (
    ModelConnectionGrantRepository,
)
from inframeld_backend.access.application.services.model_connection_grant_change_service import (
    ModelConnectionGrantChangeService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
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
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

CONNECTION = ModelConnectionId(UUID(int=452))
RECIPIENT = Principal(
    PrincipalId(UUID(int=453)), ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
ACTION = ModelConnectionAction.USE
CHANGE = ChangeModelConnectionGrantCommand(CONNECTION, RECIPIENT.id, ACTION, 7, False)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.PUT,
    f"/v1/model-connections/{CONNECTION.value}/grants/{RECIPIENT.id.value}/{ACTION.value}",
    IdempotencyKey("original"),
)
GRANT_FACTS = ModelConnectionGrantFactsDTO(
    InstallationId(UUID(int=454)),
    ORGANIZATION_ID,
    PROJECT_ID,
    CONNECTION,
    ACTION,
    7,
    FACTS.action,
    True,
    RECIPIENT,
    True,
    False,
    True,
    False,
    ActionGrantState(None),
    (),
)


class MockGrants(ModelConnectionGrantRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = GRANT_FACTS
        self.result: ModelConnectionGrantResultDTO | None = None

    @override
    async def lock_for_change(
        self, access: AccessContextDTO, command: ChangeModelConnectionGrantCommand
    ) -> ModelConnectionGrantFactsDTO:
        self.events.append("authority")
        return self.facts

    @override
    async def original(
        self, facts: ModelConnectionGrantFactsDTO, operation: CompletedSynchronousOperationDTO
    ) -> ModelConnectionGrantResultDTO:
        self.events.append("original")
        assert self.result is not None
        return replace(self.result, operation=operation)

    @override
    async def save_change(
        self,
        facts: ModelConnectionGrantFactsDTO,
        recipient_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None:
        self.events.append("save change")

    @override
    async def save_result(
        self, facts: ModelConnectionGrantFactsDTO, result: ModelConnectionGrantResultDTO
    ) -> None:
        self.events.append("save result")
        self.result = result


def _service(
    events: list[str],
) -> tuple[ModelConnectionGrantChangeService, MockGrants, MockOperationIdempotency]:
    repo = MockGrants(events)
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION
    return (
        ModelConnectionGrantChangeService(
            MockTransactions(events),
            repo,
            idempotency,
            RequestFingerprintService(RequestFingerprintKey(b"F" * 32)),
        ),
        repo,
        idempotency,
    )


@pytest.mark.asyncio
async def test_original_replays_before_fresh_revision_and_only_under_current_exact_authority() -> (
    None
):
    events: list[str] = []
    service, repo, idempotency = _service(events)
    created = await service.change(ACCESS, CHANGE, CONTEXT)
    assert created.status_code == 201 and created.changed and created.access_revision == 8
    assert created.can_grant is False and created.recipient_id == RECIPIENT.id
    assert events == [
        "begin",
        "authority",
        "reserve",
        "save change",
        "complete",
        "save result",
        "commit",
    ]

    events.clear()
    idempotency.result = replace(created.operation, created=False)
    repo.facts = replace(GRANT_FACTS, access_revision=10, recipient_is_project_member=False)
    assert await service.change(ACCESS, CHANGE, CONTEXT) == replace(
        created, operation=idempotency.result
    )
    assert events == ["begin", "authority", "reserve", "original", "commit"]

    events.clear()
    repo.facts = replace(GRANT_FACTS, actor_can_grant=False)
    with pytest.raises(AccessDeniedError):
        await service.change(ACCESS, CHANGE, CONTEXT)
    assert events == ["begin", "authority", "rollback"]


@pytest.mark.asyncio
async def test_refuses_last_grantor_loss_and_application_delegation_without_saving() -> None:
    events: list[str] = []
    service, repo, _ = _service(events)
    repo.facts = replace(GRANT_FACTS, assignment=ActionGrantState(True))
    with pytest.raises(ConflictError, match="eligible human grantor"):
        await service.change(ACCESS, CHANGE, CONTEXT)
    assert events[-1] == "rollback" and "save change" not in events

    events.clear()
    repo.facts = replace(
        GRANT_FACTS,
        recipient=replace(RECIPIENT, kind=PrincipalKind.APPLICATION),
        application_is_project_bound=True,
    )
    with pytest.raises(InvalidInputError):
        await service.change(ACCESS, replace(CHANGE, can_grant=True), CONTEXT)
    assert events[-1] == "rollback" and "save change" not in events
