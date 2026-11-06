"""Protect current management and last eligible managers before changing relationships."""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.change_access_group_relationship_command import (
    ChangeAccessGroupRelationshipCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_relationship_result_dto import (
    AccessGroupRelationshipResultDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_departure_candidate_dto import (
    ProjectDepartureCandidateDTO,
)
from inframeld_backend.access.application.enums.access_group_change_kind import (
    AccessGroupChangeKind,
)
from inframeld_backend.access.application.protocols.access_group_change_facts_reader import (
    AccessGroupChangeFactsReader,
)
from inframeld_backend.access.application.protocols.access_group_relationship_result_reader import (
    AccessGroupRelationshipResultReader,
)
from inframeld_backend.access.application.protocols.access_group_relationship_writer import (
    AccessGroupRelationshipWriter,
)
from inframeld_backend.access.application.services.access_group_relationship_service import (
    AccessGroupRelationshipService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    InvalidInputError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)

GROUP = AccessGroupId(UUID(int=10))
BOB = Principal(
    PrincipalId(UUID(int=11)), ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
ACTOR = Principal(
    ACCESS.actor_principal_id, ORGANIZATION_ID, PrincipalKind.HUMAN, PrincipalStatus.ACTIVE
)
FACTS = AccessGroupChangeFactsDTO(
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    access_revision=7,
    group_id=GROUP,
    action=ProjectActionFactsDTO(
        principal=ACTOR,
        has_pending_recovery=False,
        oauth_credential_facts=None,
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
    recipient=BOB,
    recipient_is_project_member=True,
    recipient_has_coherent_identity=True,
    recipient_has_pending_recovery=False,
    relationships=AccessGroupRelationships(member=False, manager=False),
)
COMMAND = ChangeAccessGroupRelationshipCommand(
    PROJECT_ID, GROUP, BOB.id, 7, AccessGroupChangeKind.APPOINT_MANAGER
)
CANDIDATE = ProjectDepartureCandidateDTO(
    principal=ACTOR,
    has_pending_recovery=False,
    is_project_member=True,
    has_coherent_identity=True,
    can_grant=False,
    is_group_member=True,
    is_group_manager=True,
)
ORIGINAL = AccessGroupRelationshipResultDTO(
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    group_id=GROUP,
    actor_principal_id=ACTOR.id,
    principal_id=BOB.id,
    change_kind=COMMAND.change_kind,
    access_revision=8,
    changed=True,
    relationships=AccessGroupRelationships(member=True, manager=True),
    status_code=201,
    operation=SAVED_RESULT,
)


class MockFacts(AccessGroupChangeFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts: AccessGroupChangeFactsDTO | None = FACTS
        self.candidates: tuple[ProjectDepartureCandidateDTO, ...] = (CANDIDATE,)

    @override
    async def lock_for_change(
        self, *, access: AccessContextDTO, command: ChangeAccessGroupRelationshipCommand
    ) -> AccessGroupChangeFactsDTO | None:
        self.events.append("authorize")
        return self.facts

    @override
    async def remaining_managers(
        self, *, facts: AccessGroupChangeFactsDTO, command: ChangeAccessGroupRelationshipCommand
    ) -> tuple[ProjectDepartureCandidateDTO, ...]:
        self.events.append("handover")
        return self.candidates


class MockWriter(AccessGroupRelationshipWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.results: list[AccessGroupRelationships] = []

    @override
    async def save(
        self,
        *,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        operation_id: OperationId,
        after: AccessGroupRelationships,
    ) -> None:
        self.events.append("write")
        self.results.append(after)


class MockResults(AccessGroupRelationshipResultReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result = ORIGINAL

    @override
    async def original(
        self,
        *,
        facts: AccessGroupChangeFactsDTO,
        command: ChangeAccessGroupRelationshipCommand,
        operation: CompletedSynchronousOperationDTO,
    ) -> AccessGroupRelationshipResultDTO:
        self.events.append("original")
        return self.result


class GroupScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.facts = MockFacts(self.events)
        self.writer = MockWriter(self.events)
        self.results = MockResults(self.events)
        self.idempotency = MockOperationIdempotency(self.events)
        self.idempotency.result = NEW_RESERVATION
        self.service = AccessGroupRelationshipService(
            transaction_manager=MockTransactions(self.events),
            group_change_facts_reader=self.facts,
            group_relationship_writer=self.writer,
            group_relationship_result_reader=self.results,
            operation_idempotency=self.idempotency,
            request_fingerprint_service=RequestFingerprintService(RequestFingerprintKey(b"K" * 32)),
        )

    async def change(
        self, command: ChangeAccessGroupRelationshipCommand = COMMAND
    ) -> AccessGroupRelationshipResultDTO:
        return await self.service.change(
            access=ACCESS,
            command=command,
            context=IdempotencyContextDTO(
                command.change_kind.http_method,
                f"/v1/projects/{PROJECT_ID.value}/access-groups/{GROUP.value}/{command.change_kind.collection}/{BOB.id.value}",
                IdempotencyKey("original-group-change"),
            ),
        )


@pytest.mark.asyncio
async def test_appointment_adds_both_relationships_and_advances_once() -> None:
    scenario = GroupScenario()
    result = await scenario.change()
    assert (result.relationships, result.changed, result.access_revision, result.status_code) == (
        AccessGroupRelationships(member=True, manager=True),
        True,
        8,
        201,
    )
    assert scenario.writer.results == [result.relationships]
    assert scenario.events == ["begin", "authorize", "reserve", "write", "complete", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,after",
    [
        (
            AccessGroupChangeKind.REMOVE_MANAGER,
            AccessGroupRelationships(member=True, manager=False),
        ),
        (
            AccessGroupChangeKind.REMOVE_MEMBER,
            AccessGroupRelationships(member=False, manager=False),
        ),
    ],
)
async def test_departure_keeps_an_eligible_manager_and_distinct_ordinary_membership(
    kind: AccessGroupChangeKind, after: AccessGroupRelationships
) -> None:
    scenario = GroupScenario()
    scenario.facts.facts = replace(
        FACTS, relationships=AccessGroupRelationships(member=True, manager=True)
    )
    result = await scenario.change(replace(COMMAND, change_kind=kind))
    assert (result.relationships, result.access_revision, result.status_code) == (after, 8, 200)
    assert "handover" in scenario.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "candidate_change",
    [
        "absent",
        "application",
        "suspended",
        "recovery",
        "not-project-member",
        "not-group-member",
        "not-manager",
        "incoherent",
    ],
)
async def test_last_manager_cannot_depart_relying_on_ineligible_replacement(
    candidate_change: str,
) -> None:
    scenario = GroupScenario()
    scenario.facts.facts = replace(
        FACTS, relationships=AccessGroupRelationships(member=True, manager=True)
    )
    candidate = CANDIDATE
    if candidate_change == "application":
        candidate = replace(candidate, principal=replace(ACTOR, kind=PrincipalKind.APPLICATION))
    elif candidate_change == "suspended":
        candidate = replace(candidate, principal=replace(ACTOR, status=PrincipalStatus.SUSPENDED))
    elif candidate_change == "recovery":
        candidate = replace(candidate, has_pending_recovery=True)
    elif candidate_change == "not-project-member":
        candidate = replace(candidate, is_project_member=False)
    elif candidate_change == "not-group-member":
        candidate = replace(candidate, is_group_member=False)
    elif candidate_change == "not-manager":
        candidate = replace(candidate, is_group_manager=False)
    elif candidate_change == "incoherent":
        candidate = replace(candidate, has_coherent_identity=False)
    scenario.facts.candidates = () if candidate_change == "absent" else (candidate,)
    with pytest.raises(ConflictError):
        await scenario.change(replace(COMMAND, change_kind=AccessGroupChangeKind.REMOVE_MANAGER))
    assert not scenario.writer.results and scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_add_existing_member_is_noop_and_preserves_reviewed_revision() -> None:
    scenario = GroupScenario()
    scenario.facts.facts = replace(
        FACTS, relationships=AccessGroupRelationships(member=True, manager=False)
    )
    result = await scenario.change(replace(COMMAND, change_kind=AccessGroupChangeKind.ADD_MEMBER))
    assert not result.changed and result.access_revision == 7 and result.status_code == 200
    assert "handover" not in scenario.events


@pytest.mark.asyncio
async def test_application_can_join_but_cannot_be_appointed_manager() -> None:
    scenario = GroupScenario()
    scenario.facts.facts = replace(
        FACTS,
        recipient=replace(BOB, kind=PrincipalKind.APPLICATION),
        recipient_has_coherent_identity=False,
    )
    with pytest.raises(InvalidInputError):
        await scenario.change()
    assert not scenario.writer.results
    result = await scenario.change(replace(COMMAND, change_kind=AccessGroupChangeKind.ADD_MEMBER))
    assert result.relationships == AccessGroupRelationships(member=True, manager=False)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["not-manager", "recovery", "suspended", "lost-project"])
async def test_current_authority_is_required_before_history(change: str) -> None:
    scenario = GroupScenario()
    scenario.idempotency.result = SAVED_RESULT
    action = FACTS.action
    if change == "not-manager":
        action = replace(action, has_exact_action_grant=False)
    elif change == "recovery":
        action = replace(action, has_pending_recovery=True)
    elif change == "suspended":
        action = replace(action, principal=replace(ACTOR, status=PrincipalStatus.SUSPENDED))
    else:
        action = replace(action, is_project_member=False)
    scenario.facts.facts = replace(FACTS, action=action)
    with pytest.raises((AccessDeniedError, ResourceNotFoundError)):
        await scenario.change()
    assert scenario.idempotency.calls == 0 and "original" not in scenario.events


@pytest.mark.asyncio
async def test_replay_ignores_new_recipient_ineligibility_and_never_restores_relationships() -> (
    None
):
    scenario = GroupScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.facts.facts = replace(
        FACTS, access_revision=99, recipient=None, recipient_is_project_member=False
    )
    result = await scenario.change()
    assert result == ORIGINAL and not scenario.writer.results
    assert scenario.events == ["begin", "authorize", "reserve", "original", "commit"]


@pytest.mark.asyncio
async def test_fresh_stale_review_writes_nothing() -> None:
    scenario = GroupScenario()
    with pytest.raises(StaleRevisionError):
        await scenario.change(replace(COMMAND, expected_access_revision=6))
    assert not scenario.writer.results


@pytest.mark.asyncio
async def test_application_cannot_be_a_manager_removal_recipient() -> None:
    scenario = GroupScenario()
    scenario.facts.facts = replace(FACTS, recipient=replace(BOB, kind=PrincipalKind.APPLICATION))
    with pytest.raises(InvalidInputError):
        await scenario.change(replace(COMMAND, change_kind=AccessGroupChangeKind.REMOVE_MANAGER))
    assert not scenario.writer.results


@pytest.mark.asyncio
async def test_replay_rejects_original_state_incompatible_with_appointment() -> None:
    scenario = GroupScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.results.result = replace(
        ORIGINAL, relationships=AccessGroupRelationships(member=True, manager=False)
    )
    with pytest.raises(ConflictError):
        await scenario.change()
