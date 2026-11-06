"""Preserve current Organization delegation and immutable original grant effects."""

from dataclasses import replace
from typing import override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.mock_project_metadata import (
    ACCESS,
    NEW_RESERVATION,
    ORGANIZATION_ID,
    PROJECT_ID,
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.remove_application_account_action_grant_command import (
    RemoveApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_application_account_action_grant_command import (
    SetApplicationAccountActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_action_grant_change_result_dto import (
    ApplicationAccountActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.protocols.application_account_action_grant_result_reader import (
    ApplicationAccountActionGrantResultReader,
)
from inframeld_backend.access.application.protocols.application_account_action_grant_writer import (
    ApplicationAccountActionGrantWriter,
)
from inframeld_backend.access.application.protocols.application_account_grant_management_facts_reader import (
    ApplicationAccountGrantManagementFactsReader,
)
from inframeld_backend.access.application.services.application_account_action_grant_change_service import (
    ApplicationAccountActionGrantChangeService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
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
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

ACTOR = Principal(
    id=ACCESS.actor_principal_id,
    organization_id=ORGANIZATION_ID,
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)
BOB = replace(ACTOR, id=PrincipalId(UUID(int=40)))
ACTION = ActionId("issue-application-keys")
TARGET_ID = PrincipalId(UUID(int=42))
COMMAND = SetApplicationAccountActionGrantCommand(
    project_id=PROJECT_ID,
    application_principal_id=TARGET_ID,
    recipient_principal_id=BOB.id,
    action_id=ACTION,
    can_grant=False,
    expected_access_revision=7,
)
FACTS = ApplicationAccountGrantManagementFactsDTO(
    installation_id=InstallationId(UUID(int=41)),
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    application_principal_id=TARGET_ID,
    action_id=ACTION,
    access_revision=7,
    actor=ProjectActionFactsDTO(
        principal=ACTOR,
        has_pending_recovery=False,
        oauth_credential_facts=None,
        project_status=ProjectStatus.ACTIVE,
        is_project_member=True,
        has_exact_action_grant=True,
    ),
    actor_can_grant=True,
    recipient=BOB,
    recipient_is_project_member=True,
    recipient_has_pending_recovery=False,
    recipient_has_coherent_identity=True,
    assignment=ActionGrantState(can_grant=None),
    grantors=(
        ProjectDepartureCandidatePolicyInput(
            principal=ACTOR,
            has_pending_recovery=False,
            has_coherent_identity=True,
            can_grant=True,
            is_project_member=True,
            is_group_member=False,
            is_group_manager=False,
        ),
    ),
)
ORIGINAL = ApplicationAccountActionGrantChangeResultDTO(
    installation_id=FACTS.installation_id,
    organization_id=ORGANIZATION_ID,
    project_id=PROJECT_ID,
    application_principal_id=TARGET_ID,
    actor_principal_id=ACTOR.id,
    recipient_principal_id=BOB.id,
    action_id=ACTION,
    method=HttpMethod.PUT,
    can_grant=False,
    access_revision=8,
    changed=True,
    status_code=201,
    operation=SAVED_RESULT,
)


class MockApplicationAccountGrantFacts(ApplicationAccountGrantManagementFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts: ApplicationAccountGrantManagementFactsDTO | None = FACTS

    @override
    async def lock_for_management(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ApplicationAccountGrantManagementFactsDTO | None:
        self.events.append("lock-facts")
        return self.facts


class MockApplicationAccountGrantWriter(ApplicationAccountActionGrantWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.changes: list[ActionGrantState] = []
        self.results: list[ApplicationAccountActionGrantChangeResultDTO] = []
        self.error: Exception | None = None

    @override
    async def save_change(
        self,
        *,
        facts: ApplicationAccountGrantManagementFactsDTO,
        recipient_principal_id: PrincipalId,
        after: ActionGrantState,
        operation_id: OperationId,
    ) -> None:
        self.events.append("save-change")
        if self.error is not None:
            raise self.error
        self.changes.append(after)

    @override
    async def save_result(
        self,
        *,
        result: ApplicationAccountActionGrantChangeResultDTO,
        before_revision: int,
        before_can_grant: bool | None,
    ) -> None:
        self.events.append("save-result")
        self.results.append(result)


class MockApplicationAccountGrantResults(ApplicationAccountActionGrantResultReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result = ORIGINAL

    @override
    async def original(
        self,
        *,
        facts: ApplicationAccountGrantManagementFactsDTO,
        command: SetApplicationAccountActionGrantCommand
        | RemoveApplicationAccountActionGrantCommand,
        context: IdempotencyContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        self.events.append("original")
        return self.result


class ApplicationAccountGrantScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.facts = MockApplicationAccountGrantFacts(self.events)
        self.writer = MockApplicationAccountGrantWriter(self.events)
        self.results = MockApplicationAccountGrantResults(self.events)
        self.idempotency = MockOperationIdempotency(self.events)
        self.idempotency.result = NEW_RESERVATION
        self.service = ApplicationAccountActionGrantChangeService(
            transaction_manager=MockTransactions(self.events),
            application_account_grant_facts_reader=self.facts,
            application_account_grant_writer=self.writer,
            application_account_grant_result_reader=self.results,
            operation_idempotency=self.idempotency,
            request_fingerprint_service=RequestFingerprintService(RequestFingerprintKey(b"K" * 32)),
        )

    async def set(
        self,
        command: SetApplicationAccountActionGrantCommand = COMMAND,
        *,
        access: AccessContextDTO = ACCESS,
    ) -> ApplicationAccountActionGrantChangeResultDTO:
        return await self.service.set_grant(
            access=access,
            command=command,
            context=self.context(HttpMethod.PUT, command.recipient_principal_id, command.action_id),
        )

    async def remove(self) -> ApplicationAccountActionGrantChangeResultDTO:
        return await self.service.remove_grant(
            access=ACCESS,
            command=RemoveApplicationAccountActionGrantCommand(
                project_id=PROJECT_ID,
                application_principal_id=TARGET_ID,
                recipient_principal_id=BOB.id,
                action_id=ACTION,
                expected_access_revision=7,
            ),
            context=self.context(HttpMethod.DELETE, BOB.id, ACTION),
        )

    @staticmethod
    def context(
        method: HttpMethod, recipient: PrincipalId, action: ActionId
    ) -> IdempotencyContextDTO:
        return IdempotencyContextDTO(
            method=method,
            requested_route=f"/v1/projects/{PROJECT_ID.value}/application-accounts/{TARGET_ID.value}/grants/{recipient.value}/{action.value}",
            key=IdempotencyKey("original-organization-grant"),
        )


@pytest.mark.asyncio
async def test_absent_assignment_is_created_with_one_original_revision_and_result() -> None:
    scenario = ApplicationAccountGrantScenario()

    result = await scenario.set()

    assert (result.status_code, result.changed, result.access_revision, result.can_grant) == (
        201,
        True,
        8,
        False,
    )
    assert scenario.writer.changes == [ActionGrantState(can_grant=False)]
    assert scenario.writer.results == [result]
    assert scenario.events == [
        "begin",
        "lock-facts",
        "reserve",
        "save-change",
        "complete",
        "save-result",
        "commit",
    ]
    assert scenario.idempotency.lookup_authority is not None
    assert scenario.idempotency.lookup_authority.family.value == "application_account_grant_read"


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [False, True])
async def test_existing_level_change_and_noop_keep_their_distinct_effects(previous: bool) -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.facts.facts = replace(FACTS, assignment=ActionGrantState(can_grant=previous))

    result = await scenario.set()

    assert result.status_code == 200
    assert result.changed is previous
    assert result.access_revision == 7 + int(previous)


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [None, False, True])
async def test_removal_reports_original_absence_including_an_already_absent_grant(
    previous: bool | None,
) -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.facts.facts = replace(FACTS, assignment=ActionGrantState(can_grant=previous))

    result = await scenario.remove()

    assert result.status_code == 200 and result.can_grant is None
    assert result.changed is (previous is not None)
    assert result.access_revision == 7 + int(previous is not None)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["use-only", "recovery", "suspended", "application"])
async def test_current_actor_authority_precedes_existing_history(change: str) -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.facts.facts = replace(
        FACTS,
        actor_can_grant=change != "use-only",
        actor=replace(
            FACTS.actor,
            has_pending_recovery=change == "recovery",
            principal=replace(
                ACTOR,
                status=PrincipalStatus.SUSPENDED
                if change == "suspended"
                else PrincipalStatus.ACTIVE,
                kind=PrincipalKind.APPLICATION if change == "application" else PrincipalKind.HUMAN,
            ),
        ),
    )

    with pytest.raises(AccessDeniedError):
        await scenario.set(
            access=replace(
                ACCESS, authentication_evidence=MockAuthenticationEvidence.application_key()
            )
            if change == "application"
            else ACCESS
        )

    assert scenario.idempotency.calls == 0 and "original" not in scenario.events


@pytest.mark.asyncio
async def test_replay_precedes_fresh_revision_and_recipient_checks() -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.facts.facts = replace(FACTS, access_revision=99, recipient=None)

    assert await scenario.set() == ORIGINAL
    assert not scenario.writer.changes and not scenario.writer.results
    assert scenario.events == ["begin", "lock-facts", "reserve", "original", "commit"]


@pytest.mark.asyncio
async def test_fresh_stale_review_precedes_recipient_checks_and_writes() -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.facts.facts = replace(FACTS, recipient=None)

    with pytest.raises(StaleRevisionError):
        await scenario.set(replace(COMMAND, expected_access_revision=6))

    assert not scenario.writer.changes and scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["absent", "application", "suspended", "recovery", "identity"])
async def test_fresh_assignment_rejects_ineligible_recipient_without_mutation(change: str) -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.facts.facts = replace(
        FACTS,
        recipient=None
        if change == "absent"
        else replace(
            BOB,
            kind=PrincipalKind.APPLICATION if change == "application" else PrincipalKind.HUMAN,
            status=PrincipalStatus.SUSPENDED if change == "suspended" else PrincipalStatus.ACTIVE,
        ),
        recipient_has_pending_recovery=change == "recovery",
        recipient_has_coherent_identity=change != "identity",
    )
    expected = (
        ResourceNotFoundError
        if change == "absent"
        else (InvalidInputError if change == "application" else ConflictError)
    )

    with pytest.raises(expected):
        await scenario.set()

    assert not scenario.writer.changes and scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_removal_does_not_demand_recipient_activity_or_identity_coherence() -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.facts.facts = replace(
        FACTS,
        recipient=replace(BOB, status=PrincipalStatus.SUSPENDED),
        recipient_has_pending_recovery=True,
        recipient_has_coherent_identity=False,
        assignment=ActionGrantState(can_grant=False),
    )

    result = await scenario.remove()

    assert result.changed and result.can_grant is None and result.access_revision == 8


@pytest.mark.asyncio
@pytest.mark.parametrize("remove", [False, True])
async def test_last_eligible_grantor_cannot_be_removed_or_downgraded(remove: bool) -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.facts.facts = replace(FACTS, assignment=ActionGrantState(can_grant=True), grantors=())

    with pytest.raises(ConflictError):
        await (scenario.remove() if remove else scenario.set())

    assert not scenario.writer.changes


@pytest.mark.asyncio
@pytest.mark.parametrize("noop", [False, True])
async def test_exhausted_revision_allows_only_a_noop(noop: bool) -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.facts.facts = replace(
        FACTS,
        access_revision=RevisionValidation.MAX_VALUE,
        assignment=ActionGrantState(can_grant=False if noop else None),
    )
    command = replace(COMMAND, expected_access_revision=RevisionValidation.MAX_VALUE)

    if noop:
        result = await scenario.set(command)
        assert not result.changed and result.access_revision == RevisionValidation.MAX_VALUE
    else:
        with pytest.raises(ConflictError):
            await scenario.set(command)
        assert not scenario.writer.changes


@pytest.mark.asyncio
async def test_original_receipt_cannot_change_its_recipient_or_scope() -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.results.result = replace(ORIGINAL, recipient_principal_id=ACTOR.id)

    with pytest.raises(ConflictError):
        await scenario.set()

    assert not scenario.writer.changes


@pytest.mark.asyncio
async def test_required_write_failure_rolls_back_without_completion_or_result() -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.writer.error = RuntimeError("controlled write failure")

    with pytest.raises(RuntimeError, match="controlled write failure"):
        await scenario.set()

    assert "complete" not in scenario.events and not scenario.writer.results
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_departed_human_fresh_delete_is_absent_without_rejoin() -> None:
    scenario = ApplicationAccountGrantScenario()
    scenario.facts.facts = replace(
        FACTS,
        recipient_is_project_member=False,
        recipient_has_pending_recovery=True,
        recipient_has_coherent_identity=False,
        assignment=ActionGrantState(can_grant=None),
    )
    result = await scenario.remove()
    assert result.status_code == 200 and not result.changed and result.can_grant is None
    assert result.access_revision == FACTS.access_revision
    assert scenario.facts.facts.recipient_is_project_member is False
    assert scenario.facts.facts.assignment.can_grant is None
