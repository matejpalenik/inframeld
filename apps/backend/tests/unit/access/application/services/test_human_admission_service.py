import asyncio
from dataclasses import replace
from datetime import timedelta
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence
from tests.support.human_admission_scenarios import (
    ACCESS,
    ACTOR_FACTS,
    ALICE,
    BOB,
    COMMAND,
    CONTEXT,
    FACTS,
    IDENTITY,
    INSTALLATION,
    ORG,
    HumanAdmissionScenario,
)
from tests.support.mock_project_metadata import NEW_RESERVATION

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.errors.human_oauth_credential_rejected_error import (
    HumanOAuthCredentialRejectedError,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    AuthenticationRequiredError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)


@pytest.mark.asyncio
async def test_new_admission_closes_preliminary_tx_before_provider_then_saves_once() -> None:
    s = HumanAdmissionScenario()
    s.idempotency.result = NEW_RESERVATION
    result = await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert s.events == [
        "begin",
        "preliminary",
        "commit",
        "verify",
        "begin",
        "fresh-facts",
        "reserve",
        "save",
        "complete",
        "commit",
    ]
    assert result.changed and result.access_revision == 8
    assert result.identity == IDENTITY and result.installation_id == INSTALLATION
    assert result.organization_id == ORG and result.actor_principal_id == ALICE.id
    assert s.writer.saved is not None and result.principal_id == s.writer.saved.id
    assert s.writer.saved.kind is PrincipalKind.HUMAN
    assert s.writer.saved.status is PrincipalStatus.ACTIVE
    assert s.idempotency.lookup_authority is not None
    assert s.idempotency.lookup_authority.action_id is not None
    assert s.idempotency.lookup_authority.action_id.value == "admit-users"


@pytest.mark.asyncio
async def test_fresh_already_admitted_preserves_principal_missing_version_and_revision() -> None:
    s = HumanAdmissionScenario()
    s.already_admitted()
    s.idempotency.result = NEW_RESERVATION
    result = await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert not result.changed and result.principal_id == BOB.id and result.access_revision == 7
    assert s.writer.saved is BOB and s.writer.saved_facts is s.facts.final
    assert s.writer.saved_facts is not None
    assert s.writer.saved_facts.credential_state.version is None
    assert s.events.count("save") == s.events.count("complete") == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", [True, False])
async def test_replay_returns_original_status_revision_and_expiry_without_writes(
    changed: bool,
) -> None:
    s = HumanAdmissionScenario()
    s.already_admitted()
    s.results.result = replace(s.results.result, changed=changed)
    assert s.facts.final is not None
    s.facts.final = replace(s.facts.final, actor=replace(ACTOR_FACTS, access_revision=50))
    result = await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert result is s.results.result and result.changed is changed
    assert (
        result.access_revision == 8
        and result.operation.expires_at == s.results.result.operation.expires_at
    )
    assert s.writer.saved is None and "complete" not in s.events
    assert s.events[-3:] == ["reserve", "original", "commit"]


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["preliminary", "final"])
@pytest.mark.parametrize("denial", ["missing", "grant", "suspended", "recovery"])
async def test_current_alice_denial_prevents_disclosure_and_writes(phase: str, denial: str) -> None:
    s = HumanAdmissionScenario()
    denied = ACTOR_FACTS
    if denial == "grant":
        denied = replace(denied, grants=())
    if denial == "suspended":
        denied = replace(denied, principal=replace(ALICE, status=PrincipalStatus.SUSPENDED))
    if denial == "recovery":
        denied = replace(denied, has_pending_recovery=True)
    if phase == "preliminary":
        s.facts.preliminary = None if denial == "missing" else denied
    else:
        s.facts.final = None if denial == "missing" else replace(FACTS, actor=denied)
    with pytest.raises(ResourceNotFoundError if denial == "missing" else AccessDeniedError):
        await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert "reserve" not in s.events and "original" not in s.events and s.writer.saved is None
    assert ("verify" in s.events) is (phase == "final")


@pytest.mark.asyncio
async def test_current_oauth_generation_is_rechecked_after_provider() -> None:
    from tests.support.authentication_evidence import MockAuthenticationEvidence

    from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO

    s = HumanAdmissionScenario()
    access = AccessContextDTO(ALICE.id, MockAuthenticationEvidence.human_oauth())
    s.facts.preliminary = replace(
        ACTOR_FACTS,
        oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(1)),
    )
    s.facts.final = replace(
        FACTS,
        actor=replace(
            ACTOR_FACTS,
            oauth_credential_facts=HumanCredentialFactsDTO(True, HumanCredentialVersion(2)),
        ),
    )
    with pytest.raises(HumanOAuthCredentialRejectedError):
        await s.service.admit(access=access, command=COMMAND, context=CONTEXT)
    assert "reserve" not in s.events and s.writer.saved is None


@pytest.mark.asyncio
@pytest.mark.parametrize("blocked", ["suspended", "application", "recovery", "foreign"])
async def test_current_bob_denial_precedes_business_replay(blocked: str) -> None:
    s = HumanAdmissionScenario()
    s.already_admitted()
    principal = BOB
    if blocked == "suspended":
        principal = replace(BOB, status=PrincipalStatus.SUSPENDED)
    if blocked == "application":
        principal = replace(BOB, kind=PrincipalKind.APPLICATION)
    if blocked == "foreign":
        principal = replace(BOB, organization_id=type(ORG)(UUID(int=999)))
    s.facts.final = replace(
        FACTS,
        principal=principal,
        credential_state=replace(
            FACTS.credential_state, has_pending_recovery=blocked == "recovery"
        ),
    )
    with pytest.raises(ConflictError):
        await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert "reserve" not in s.events and "original" not in s.events and s.writer.saved is None


@pytest.mark.asyncio
async def test_completed_recovery_history_with_current_generation_allows_original_replay() -> None:
    s = HumanAdmissionScenario()
    s.facts.final = replace(
        FACTS,
        principal=BOB,
        has_credential_history=True,
        credential_state=replace(FACTS.credential_state, version=HumanCredentialVersion(8)),
    )
    assert (
        await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT) is s.results.result
    )
    assert s.writer.saved is None


@pytest.mark.asyncio
@pytest.mark.parametrize("admitted", [True, False])
async def test_missing_generation_with_history_fails_closed_without_repair(admitted: bool) -> None:
    s = HumanAdmissionScenario()
    s.facts.final = replace(FACTS, principal=BOB if admitted else None, has_credential_history=True)
    with pytest.raises(DependencyUnavailableError):
        await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert "reserve" not in s.events and s.writer.saved is None


@pytest.mark.asyncio
async def test_provider_inactive_rejects_before_final_work() -> None:
    s = HumanAdmissionScenario()
    s.verifier.result = None
    with pytest.raises(ConflictError):
        await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert s.events == ["begin", "preliminary", "commit", "verify"]


@pytest.mark.asyncio
async def test_new_request_checks_fresh_revision_before_save() -> None:
    s = HumanAdmissionScenario()
    s.idempotency.result = NEW_RESERVATION
    with pytest.raises(StaleRevisionError):
        await s.service.admit(
            access=ACCESS, command=replace(COMMAND, expected_access_revision=6), context=CONTEXT
        )
    assert s.writer.saved is None and "complete" not in s.events


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mismatch", ["actor", "identity", "installation", "principal", "operation", "expiry"]
)
async def test_incoherent_original_result_never_replays(mismatch: str) -> None:
    s = HumanAdmissionScenario()
    s.already_admitted()
    original = s.results.result
    if mismatch == "actor":
        original = replace(original, actor_principal_id=PrincipalId(UUID(int=99)))
    if mismatch == "identity":
        original = replace(
            original, identity=replace(IDENTITY, subject=type(IDENTITY.subject)(str(UUID(int=99))))
        )
    if mismatch == "installation":
        original = replace(original, installation_id=type(INSTALLATION)(UUID(int=99)))
    if mismatch == "principal":
        original = replace(original, principal_id=PrincipalId(UUID(int=99)))
    if mismatch == "operation":
        original = replace(
            original,
            operation=replace(
                original.operation, operation_id=type(original.operation.operation_id)("other")
            ),
        )
    if mismatch == "expiry":
        original = replace(
            original,
            operation=replace(
                original.operation, expires_at=original.operation.expires_at + timedelta(days=1)
            ),
        )
    s.results.result = original
    with pytest.raises(ConflictError):
        await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert s.writer.saved is None and "complete" not in s.events


@pytest.mark.asyncio
@pytest.mark.parametrize("phase", ["provider", "facts", "writer", "completion", "commit"])
async def test_failures_and_cancellation_propagate_to_transaction_owner(phase: str) -> None:
    s = HumanAdmissionScenario()
    s.idempotency.result = NEW_RESERVATION
    error = asyncio.CancelledError() if phase == "writer" else RuntimeError("controlled failure")
    if phase == "provider":
        s.verifier.error = error
    if phase == "facts":
        s.facts.error = error
    if phase == "writer":
        s.writer.error = error
    if phase == "completion":
        assert isinstance(error, Exception)
        s.idempotency.completion_error = error
    if phase == "commit":
        s.transactions.commit_error = error
    with pytest.raises(type(error)) as caught:
        await s.service.admit(access=ACCESS, command=COMMAND, context=CONTEXT)
    assert caught.value is error and not s.transactions.active
    if phase != "provider":
        assert s.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_wrong_operation_route_is_rejected_before_work() -> None:
    s = HumanAdmissionScenario()
    with pytest.raises(RuntimeError, match="original operation route"):
        await s.service.admit(
            access=ACCESS,
            command=COMMAND,
            context=replace(CONTEXT, requested_route="/v1/organizations/foreign/human-admissions"),
        )
    assert s.events == []


@pytest.mark.asyncio
@pytest.mark.parametrize("oauth", [False, True])
@pytest.mark.parametrize("phase", ["preliminary", "final"])
async def test_browser_currentness_preserves_the_presented_credential_family(
    oauth: bool, phase: str
) -> None:
    """Reject stale evidence before disclosing data, recovering originals or changing authority."""
    evidence = (
        MockAuthenticationEvidence.human_oauth() if oauth else MockAuthenticationEvidence.browser()
    )
    stale = HumanCredentialFactsDTO(True, HumanCredentialVersion(2))
    expected = HumanOAuthCredentialRejectedError if oauth else AuthenticationRequiredError
    scenario = HumanAdmissionScenario()
    denied = replace(ACTOR_FACTS, oauth_credential_facts=stale)
    if phase == "preliminary":
        scenario.facts.preliminary = denied
    else:
        scenario.facts.final = replace(FACTS, actor=denied)
    with pytest.raises(AuthenticationRequiredError) as caught:
        await scenario.service.admit(
            access=AccessContextDTO(ALICE.id, evidence), command=COMMAND, context=CONTEXT
        )
    assert type(caught.value) is expected
    assert "reserve" not in scenario.events and "original" not in scenario.events
    assert scenario.writer.saved is None
    assert ("verify" in scenario.events) is (phase == "final")
