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
    SAVED_RESULT,
    MockOperationIdempotency,
    MockTransactions,
)

from inframeld_backend.access.application.commands.remove_organization_action_grant_command import (
    RemoveOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.commands.set_organization_action_grant_command import (
    SetOrganizationActionGrantCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_change_result_dto import (
    OrganizationActionGrantChangeResultDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.application.protocols.organization_action_grant_result_reader import (
    OrganizationActionGrantResultReader,
)
from inframeld_backend.access.application.protocols.organization_action_grant_writer import (
    OrganizationActionGrantWriter,
)
from inframeld_backend.access.application.protocols.organization_grant_management_facts_reader import (
    OrganizationGrantManagementFactsReader,
)
from inframeld_backend.access.application.services.organization_action_grant_change_service import (
    OrganizationActionGrantChangeService,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.policy_inputs.organization_grant_candidate_policy_input import (
    OrganizationGrantCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import IdempotencyContextDTO
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
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
ACTION = ActionId("create-projects")
COMMAND = SetOrganizationActionGrantCommand(
    organization_id=ORGANIZATION_ID,
    recipient_principal_id=BOB.id,
    action_id=ACTION,
    can_grant=False,
    expected_access_revision=7,
)
FACTS = OrganizationGrantManagementFactsDTO(
    installation_id=InstallationId(UUID(int=41)),
    organization_id=ORGANIZATION_ID,
    action_id=ACTION,
    access_revision=7,
    actor=ACTOR,
    actor_can_grant=True,
    actor_has_pending_recovery=False,
    actor_oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
    recipient=BOB,
    recipient_has_pending_recovery=False,
    recipient_has_coherent_identity=True,
    assignment=ActionGrantState(can_grant=None),
    other_grantors=(
        OrganizationGrantCandidatePolicyInput(
            principal=ACTOR,
            has_pending_recovery=False,
            has_coherent_identity=True,
            can_grant=True,
        ),
    ),
)
ORIGINAL = OrganizationActionGrantChangeResultDTO(
    installation_id=FACTS.installation_id,
    organization_id=ORGANIZATION_ID,
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


class MockOrganizationGrantFacts(OrganizationGrantManagementFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts: OrganizationGrantManagementFactsDTO | None = FACTS

    @override
    async def lock_for_management(
        self,
        *,
        access: AccessContextDTO,
        organization_id: OrganizationId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> OrganizationGrantManagementFactsDTO | None:
        self.events.append("lock-facts")
        return self.facts


class MockOrganizationGrantWriter(OrganizationActionGrantWriter):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.changes: list[ActionGrantState] = []
        self.results: list[OrganizationActionGrantChangeResultDTO] = []
        self.error: Exception | None = None

    @override
    async def save_change(
        self,
        *,
        facts: OrganizationGrantManagementFactsDTO,
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
        result: OrganizationActionGrantChangeResultDTO,
        before_revision: int,
        before_can_grant: bool | None,
    ) -> None:
        self.events.append("save-result")
        self.results.append(result)


class MockOrganizationGrantResults(OrganizationActionGrantResultReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result = ORIGINAL

    @override
    async def original(
        self,
        *,
        facts: OrganizationGrantManagementFactsDTO,
        command: SetOrganizationActionGrantCommand | RemoveOrganizationActionGrantCommand,
        context: IdempotencyContextDTO,
        operation: CompletedSynchronousOperationDTO,
    ) -> OrganizationActionGrantChangeResultDTO:
        self.events.append("original")
        return self.result


class OrganizationGrantScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.facts = MockOrganizationGrantFacts(self.events)
        self.writer = MockOrganizationGrantWriter(self.events)
        self.results = MockOrganizationGrantResults(self.events)
        self.idempotency = MockOperationIdempotency(self.events)
        self.idempotency.result = NEW_RESERVATION
        self.service = OrganizationActionGrantChangeService(
            transaction_manager=MockTransactions(self.events),
            organization_grant_facts_reader=self.facts,
            organization_grant_writer=self.writer,
            organization_grant_result_reader=self.results,
            operation_idempotency=self.idempotency,
            request_fingerprint_service=RequestFingerprintService(RequestFingerprintKey(b"K" * 32)),
        )

    async def set(
        self,
        command: SetOrganizationActionGrantCommand = COMMAND,
        *,
        access: AccessContextDTO = ACCESS,
    ) -> OrganizationActionGrantChangeResultDTO:
        return await self.service.set_grant(
            access=access,
            command=command,
            context=self.context(HttpMethod.PUT, command.recipient_principal_id, command.action_id),
        )

    async def remove(self) -> OrganizationActionGrantChangeResultDTO:
        return await self.service.remove_grant(
            access=ACCESS,
            command=RemoveOrganizationActionGrantCommand(
                organization_id=ORGANIZATION_ID,
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
            requested_route=f"/v1/organizations/{ORGANIZATION_ID.value}/grants/{recipient.value}/{action.value}",
            key=IdempotencyKey("original-organization-grant"),
        )


@pytest.mark.asyncio
async def test_absent_assignment_is_created_with_one_original_revision_and_result() -> None:
    scenario = OrganizationGrantScenario()

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
    assert scenario.idempotency.lookup_authority.family.value == "organization_grant_read"


@pytest.mark.asyncio
@pytest.mark.parametrize("previous", [False, True])
async def test_existing_level_change_and_noop_keep_their_distinct_effects(previous: bool) -> None:
    scenario = OrganizationGrantScenario()
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
    scenario = OrganizationGrantScenario()
    scenario.facts.facts = replace(FACTS, assignment=ActionGrantState(can_grant=previous))

    result = await scenario.remove()

    assert result.status_code == 200 and result.can_grant is None
    assert result.changed is (previous is not None)
    assert result.access_revision == 7 + int(previous is not None)


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["use-only", "recovery", "suspended", "application"])
async def test_current_actor_authority_precedes_existing_history(change: str) -> None:
    scenario = OrganizationGrantScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.facts.facts = replace(
        FACTS,
        actor_can_grant=change != "use-only",
        actor_has_pending_recovery=change == "recovery",
        actor=replace(
            ACTOR,
            status=PrincipalStatus.SUSPENDED if change == "suspended" else PrincipalStatus.ACTIVE,
            kind=PrincipalKind.APPLICATION if change == "application" else PrincipalKind.HUMAN,
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
    scenario = OrganizationGrantScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.facts.facts = replace(FACTS, access_revision=99, recipient=None)

    assert await scenario.set() == ORIGINAL
    assert not scenario.writer.changes and not scenario.writer.results
    assert scenario.events == ["begin", "lock-facts", "reserve", "original", "commit"]


@pytest.mark.asyncio
async def test_fresh_stale_review_precedes_recipient_checks_and_writes() -> None:
    scenario = OrganizationGrantScenario()
    scenario.facts.facts = replace(FACTS, recipient=None)

    with pytest.raises(StaleRevisionError):
        await scenario.set(replace(COMMAND, expected_access_revision=6))

    assert not scenario.writer.changes and scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["absent", "application", "suspended", "recovery", "identity"])
async def test_fresh_assignment_rejects_ineligible_recipient_without_mutation(change: str) -> None:
    scenario = OrganizationGrantScenario()
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
    scenario = OrganizationGrantScenario()
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
    scenario = OrganizationGrantScenario()
    scenario.facts.facts = replace(
        FACTS, assignment=ActionGrantState(can_grant=True), other_grantors=()
    )

    with pytest.raises(ConflictError):
        await (scenario.remove() if remove else scenario.set())

    assert not scenario.writer.changes


@pytest.mark.asyncio
@pytest.mark.parametrize("noop", [False, True])
async def test_exhausted_revision_allows_only_a_noop(noop: bool) -> None:
    scenario = OrganizationGrantScenario()
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
    scenario = OrganizationGrantScenario()
    scenario.idempotency.result = SAVED_RESULT
    scenario.results.result = replace(ORIGINAL, recipient_principal_id=ACTOR.id)

    with pytest.raises(ConflictError):
        await scenario.set()

    assert not scenario.writer.changes


@pytest.mark.asyncio
async def test_required_write_failure_rolls_back_without_completion_or_result() -> None:
    scenario = OrganizationGrantScenario()
    scenario.writer.error = RuntimeError("controlled write failure")

    with pytest.raises(RuntimeError, match="controlled write failure"):
        await scenario.set()

    assert "complete" not in scenario.events and not scenario.writer.results
    assert scenario.events[-1] == "rollback"


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
async def test_browser_currentness_preserves_the_presented_credential_family(oauth: bool) -> None:
    """Reject stale evidence before disclosing data, recovering originals or changing authority."""
    evidence = (
        MockAuthenticationEvidence.human_oauth() if oauth else MockAuthenticationEvidence.browser()
    )
    stale = HumanCredentialFactsDTO(True, HumanCredentialVersion(2))
    expected = HumanOAuthCredentialRejectedError if oauth else AuthenticationRequiredError
    scenario = OrganizationGrantScenario()
    scenario.facts.facts = replace(FACTS, actor_oauth_credential_facts=stale)
    with pytest.raises(AuthenticationRequiredError) as caught:
        await scenario.set(access=replace(ACCESS, authentication_evidence=evidence))
    assert type(caught.value) is expected
    assert scenario.events == ["begin", "lock-facts", "rollback"]
    assert scenario.writer.changes == [] and scenario.writer.results == []
