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

from inframeld_backend.access.application.commands.change_processing_profile_grant_command import (
    ChangeProcessingProfileGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.processing_profile_grant_facts_dto import (
    ProcessingProfileGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_item_dto import (
    ProcessingProfileGrantItemDTO,
)
from inframeld_backend.access.application.dtos.processing_profile_grant_result_dto import (
    ProcessingProfileGrantResultDTO,
)
from inframeld_backend.access.application.protocols.processing_profile_grant_repository import (
    ProcessingProfileGrantRepository,
)
from inframeld_backend.access.application.services.processing_profile_grant_change_service import (
    ProcessingProfileGrantChangeService,
)
from inframeld_backend.access.application.services.processing_profile_grants_read_service import (
    ProcessingProfileGrantsReadService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.indexing.domain.value_objects.processing_profile_id import (
    ProcessingProfileId,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

PROFILE = ProcessingProfileId(UUID(int=452))
RECIPIENT = Principal(
    PrincipalId(UUID(int=453)), ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
ACTION = ProcessingProfileAction.USE
CHANGE = ChangeProcessingProfileGrantCommand(PROFILE, RECIPIENT.id, ACTION, 7, False)
CONTEXT = IdempotencyContextDTO(
    HttpMethod.PUT,
    f"/v1/processing-profiles/{PROFILE.value}/grants/{RECIPIENT.id.value}/{ACTION.value}",
    IdempotencyKey("original"),
)
GRANT_FACTS = ProcessingProfileGrantFactsDTO(
    InstallationId(UUID(int=454)),
    ORGANIZATION_ID,
    PROJECT_ID,
    PROFILE,
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


class MockGrants(ProcessingProfileGrantRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = GRANT_FACTS
        self.result: ProcessingProfileGrantResultDTO | None = None

    @override
    async def lock_for_read(
        self,
        access: AccessContextDTO,
        profile_id: ProcessingProfileId,
        action: ProcessingProfileAction,
    ) -> ProcessingProfileGrantFactsDTO:
        self.events.append("authority")
        return self.facts

    @override
    async def list_assignments(
        self, facts: ProcessingProfileGrantFactsDTO, after: PrincipalId | None, limit: int
    ) -> tuple[ProcessingProfileGrantItemDTO, ...]:
        raise AssertionError("A change does not list assignments.")

    @override
    async def lock_for_change(
        self, access: AccessContextDTO, command: ChangeProcessingProfileGrantCommand
    ) -> ProcessingProfileGrantFactsDTO:
        self.events.append("authority")
        return self.facts

    @override
    async def original(
        self, facts: ProcessingProfileGrantFactsDTO, operation: CompletedSynchronousOperationDTO
    ) -> ProcessingProfileGrantResultDTO:
        self.events.append("original")
        assert self.result is not None
        return replace(self.result, operation=operation)

    @override
    async def save_change(
        self,
        facts: ProcessingProfileGrantFactsDTO,
        recipient_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None:
        self.events.append("save change")

    @override
    async def save_result(
        self, facts: ProcessingProfileGrantFactsDTO, result: ProcessingProfileGrantResultDTO
    ) -> None:
        self.events.append("save result")
        self.result = result


def _service(
    events: list[str],
) -> tuple[ProcessingProfileGrantChangeService, MockGrants, MockOperationIdempotency]:
    repo = MockGrants(events)
    idempotency = MockOperationIdempotency(events)
    idempotency.result = NEW_RESERVATION
    return (
        ProcessingProfileGrantChangeService(
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("facts", "error"),
    [
        (
            replace(
                GRANT_FACTS,
                actor_can_grant=False,
                actor=replace(GRANT_FACTS.actor, has_exact_action_grant=True),
            ),
            AccessDeniedError,
        ),
        (
            replace(
                GRANT_FACTS, actor=replace(GRANT_FACTS.actor, project_status=ProjectStatus.DELETING)
            ),
            ResourceNotFoundError,
        ),
        (replace(GRANT_FACTS, organization_id=OrganizationId(UUID(int=999))), RuntimeError),
    ],
    ids=("use-only", "inactive-project", "wrong-organization"),
)
async def test_each_grant_operation_rejects_unsafe_scope_before_effects_or_replay(
    facts: ProcessingProfileGrantFactsDTO, error: type[Exception]
) -> None:
    events: list[str] = []
    changer, repo, idempotency = _service(events)
    reader = ProcessingProfileGrantsReadService(MockTransactions(events), repo)
    repo.facts = facts

    for method in (HttpMethod.PUT, HttpMethod.DELETE):
        events.clear()
        command = CHANGE if method is HttpMethod.PUT else replace(CHANGE, can_grant=None)
        with pytest.raises(error):
            await changer.change(ACCESS, command, replace(CONTEXT, method=method))
        assert events == ["begin", "authority", "rollback"]
        assert idempotency.calls == 0

    events.clear()
    with pytest.raises(error):
        await reader.list_grants(ACCESS, PROFILE, ACTION, 25, None)
    assert events == ["begin", "authority", "rollback"]
