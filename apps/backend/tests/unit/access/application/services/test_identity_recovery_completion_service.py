from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal, override
from uuid import UUID

import pytest
from tests.support.mock_identity_recovery_cleanup_proofs import MockIdentityRecoveryCleanupProofs

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_completion_facts_dto import (
    IdentityRecoveryCompletionFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_facts_reader import (
    IdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_repository import (
    IdentityRecoveryRepository,
)
from inframeld_backend.access.application.services.identity_recovery_completion_service import (
    IdentityRecoveryCompletionService,
)
from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.errors.identity_recovery_errors import (
    IdentityRecoveryTransitionError,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
    InvalidInputError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

INSTALLATION = InstallationId(UUID(int=1))
AUTHORITY = IdentityAuthority("kratos")
EVENT = IdentityRecoveryEventDTO(
    flow_id=IdentityRecoveryFlowId(UUID(int=2)),
    identity=VerifiedHumanIdentityDTO(authority=AUTHORITY, subject=IdentitySubject("alice")),
    event_kind=IdentityRecoveryEventKind.RECOVERY,
)
OPERATION = OperationId("original-operation")
ALICE = Principal(
    id=PrincipalId(UUID(int=3)),
    organization_id=OrganizationId(UUID(int=4)),
    kind=PrincipalKind.HUMAN,
    status=PrincipalStatus.ACTIVE,
)


class MockTransactionManager(TransactionManager):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.commit_error: Exception | None = None

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        else:
            if self.commit_error is not None:
                self.events.append("commit-failed")
                raise self.commit_error
            self.events.append("commit")


class MockIdentityRecoveryCompletionFactsReader(IdentityRecoveryCompletionFactsReader):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.facts = IdentityRecoveryCompletionFactsDTO(
            installation_id=INSTALLATION,
            admission=IdentityRecoveryAdmissionDTO(event=EVENT, operation_id=OPERATION),
            principal=ALICE,
            has_other_pending_recovery=False,
            credential_version=HumanCredentialVersion(2),
        )
        self.error: Exception | None = None
        self.calls: list[tuple[InstallationId, IdentityAuthority, IdentityRecoveryFlowId]] = []

    @override
    async def read(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecoveryCompletionFactsDTO:
        self.events.append("facts")
        self.calls.append((installation_id, authority, flow_id))
        if self.error is not None:
            raise self.error
        return self.facts


class MockIdentityRecoveryRepository(IdentityRecoveryRepository):
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.recovery = IdentityRecovery(
            installation_id=INSTALLATION,
            authority=AUTHORITY,
            flow_id=EVENT.flow_id,
            subject=EVENT.identity.subject,
        )
        self.get_error: Exception | None = None
        self.save_error: BaseException | None = None
        self.calls: list[tuple[InstallationId, IdentityAuthority, IdentityRecoveryFlowId]] = []
        self.saved: list[IdentityRecovery] = []

    @override
    async def get(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecovery:
        self.events.append("load")
        self.calls.append((installation_id, authority, flow_id))
        if self.get_error is not None:
            raise self.get_error
        return self.recovery

    @override
    async def save(self, recovery: IdentityRecovery) -> None:
        self.events.append("save")
        if self.save_error is not None:
            raise self.save_error
        self.saved.append(recovery)


class MockCompletionScenario:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.transactions = MockTransactionManager(self.events)
        self.facts = MockIdentityRecoveryCompletionFactsReader(self.events)
        self.recoveries = MockIdentityRecoveryRepository(self.events)
        self.proofs = MockIdentityRecoveryCleanupProofs(self.facts.facts.admission)
        self.service = IdentityRecoveryCompletionService(
            self.transactions,
            self.facts,
            self.recoveries,
            installation_id=INSTALLATION,
            authority=AUTHORITY,
            proofs=self.proofs,
            proof_writer=self.proofs,
        )


@pytest.mark.asyncio
async def test_confirmed_cleanup_commits_before_returning_original_operation() -> None:
    scenario = MockCompletionScenario()
    before = datetime.now(UTC)

    result = await scenario.service.record_cleanup(
        event=EVENT,
        kratos_outcome=IdentityRecoveryCleanupState.CONFIRMED,
        hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED,
    )

    assert scenario.events == ["begin", "facts", "load", "save", "commit"]
    assert scenario.facts.calls == [(INSTALLATION, AUTHORITY, EVENT.flow_id)]
    assert scenario.recoveries.calls == [(INSTALLATION, AUTHORITY, EVENT.flow_id)]
    assert scenario.recoveries.saved == [scenario.recoveries.recovery]
    assert result.operation_id == OPERATION
    assert result.released_at is not None
    assert before <= result.released_at <= datetime.now(UTC)
    assert not result.has_other_pending_recovery


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "outcome",
    [
        IdentityRecoveryCleanupState.CONFIRMED,
        IdentityRecoveryCleanupState.FAILED,
        IdentityRecoveryCleanupState.UNCERTAIN,
    ],
)
async def test_partial_cleanup_preserves_omitted_provider_and_keeps_block(
    outcome: IdentityRecoveryCleanupState,
) -> None:
    scenario = MockCompletionScenario()

    result = await scenario.service.record_cleanup(event=EVENT, kratos_outcome=outcome)

    assert result.kratos_cleanup_state is outcome
    assert result.hydra_cleanup_state is IdentityRecoveryCleanupState.PENDING
    assert result.released_at is None
    assert scenario.events[-1] == "commit"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "principal",
    [
        None,
        replace(ALICE, status=PrincipalStatus.SUSPENDED),
        replace(ALICE, status=PrincipalStatus.RETIRED),
    ],
)
async def test_release_uses_current_local_eligibility(principal: Principal | None) -> None:
    """No account is provisioned, and a local suspension or retirement is preserved."""
    scenario = MockCompletionScenario()
    scenario.facts.facts = replace(scenario.facts.facts, principal=principal)

    result = await scenario.service.record_cleanup(
        event=EVENT,
        kratos_outcome=IdentityRecoveryCleanupState.CONFIRMED,
        hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED,
    )

    assert (result.released_at is not None) is (principal is None)
    assert scenario.facts.facts.principal is principal


@pytest.mark.asyncio
async def test_other_recovery_is_reported_without_preventing_this_release() -> None:
    scenario = MockCompletionScenario()
    scenario.facts.facts = replace(scenario.facts.facts, has_other_pending_recovery=True)

    result = await scenario.service.record_cleanup(
        event=EVENT,
        kratos_outcome=IdentityRecoveryCleanupState.CONFIRMED,
        hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED,
    )

    assert result.released_at is not None
    assert result.has_other_pending_recovery


@pytest.mark.asyncio
async def test_released_duplicate_preserves_results_and_does_not_save() -> None:
    """Delayed evidence cannot restart or regress an already released recovery."""
    scenario = MockCompletionScenario()
    released_at = datetime(2026, 10, 23, tzinfo=UTC)
    scenario.recoveries.recovery = IdentityRecovery(
        installation_id=INSTALLATION,
        authority=AUTHORITY,
        flow_id=EVENT.flow_id,
        subject=EVENT.identity.subject,
        kratos_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
        hydra_cleanup_state=IdentityRecoveryCleanupState.CONFIRMED,
        released_at=released_at,
    )

    result = await scenario.service.record_cleanup(
        event=EVENT, hydra_outcome=IdentityRecoveryCleanupState.UNCERTAIN
    )

    assert result.released_at == released_at
    assert result.hydra_cleanup_state is IdentityRecoveryCleanupState.CONFIRMED
    assert scenario.recoveries.saved == []
    assert scenario.events == ["begin", "facts", "load", "commit"]


@pytest.mark.asyncio
async def test_unreleased_repeat_rechecks_account_after_restoration() -> None:
    scenario = MockCompletionScenario()
    scenario.facts.facts = replace(
        scenario.facts.facts, principal=replace(ALICE, status=PrincipalStatus.SUSPENDED)
    )
    first = await scenario.service.record_cleanup(
        event=EVENT,
        kratos_outcome=IdentityRecoveryCleanupState.CONFIRMED,
        hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED,
    )
    assert first.released_at is None

    scenario.facts.facts = replace(scenario.facts.facts, principal=ALICE)
    repeated = await scenario.service.record_cleanup(
        event=EVENT, hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED
    )

    assert repeated.operation_id == first.operation_id
    assert repeated.released_at is not None
    assert len(scenario.facts.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kratos,hydra",
    [
        (None, None),
        (IdentityRecoveryCleanupState.PENDING, None),
        (None, IdentityRecoveryCleanupState.PENDING),
    ],
)
async def test_invalid_outcome_input_never_opens_a_transaction(
    kratos: IdentityRecoveryCleanupState | None, hydra: IdentityRecoveryCleanupState | None
) -> None:
    scenario = MockCompletionScenario()
    with pytest.raises(InvalidInputError):
        await scenario.service.record_cleanup(
            event=EVENT, kratos_outcome=kratos, hydra_outcome=hydra
        )
    assert scenario.events == []


@pytest.mark.asyncio
async def test_wrong_configured_provider_never_reaches_persistence() -> None:
    scenario = MockCompletionScenario()
    event = replace(EVENT, identity=replace(EVENT.identity, authority=IdentityAuthority("other")))
    with pytest.raises(ConflictError):
        await scenario.service.record_cleanup(
            event=event, hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED
        )
    assert scenario.events == []


@pytest.mark.asyncio
async def test_missing_admission_conflicts_without_creating_an_obligation() -> None:
    scenario = MockCompletionScenario()
    scenario.facts.error = ResourceNotFoundError()
    with pytest.raises(ConflictError) as error:
        await scenario.service.record_cleanup(
            event=EVENT, hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED
        )
    assert isinstance(error.value.__cause__, ResourceNotFoundError)
    assert scenario.events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "event",
    [
        replace(EVENT, identity=replace(EVENT.identity, subject=IdentitySubject("bob"))),
        replace(EVENT, event_kind=IdentityRecoveryEventKind.PASSWORD_RESET),
    ],
)
async def test_conflicting_event_cannot_load_or_change_the_checklist(
    event: IdentityRecoveryEventDTO,
) -> None:
    scenario = MockCompletionScenario()
    with pytest.raises(ConflictError):
        await scenario.service.record_cleanup(
            event=event, kratos_outcome=IdentityRecoveryCleanupState.CONFIRMED
        )
    assert scenario.events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
async def test_facts_from_another_installation_fail_before_loading() -> None:
    scenario = MockCompletionScenario()
    scenario.facts.facts = replace(
        scenario.facts.facts, installation_id=InstallationId(UUID(int=99))
    )
    with pytest.raises(RuntimeError):
        await scenario.service.record_cleanup(
            event=EVENT, hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED
        )
    assert scenario.events == ["begin", "facts", "rollback"]


@pytest.mark.asyncio
@pytest.mark.parametrize("scope", ["installation", "authority", "flow", "subject"])
async def test_loaded_checklist_must_match_the_original_target(
    scope: Literal["installation", "authority", "flow", "subject"],
) -> None:
    scenario = MockCompletionScenario()
    scenario.recoveries.recovery = IdentityRecovery(
        installation_id=InstallationId(UUID(int=99)) if scope == "installation" else INSTALLATION,
        authority=IdentityAuthority("other") if scope == "authority" else AUTHORITY,
        flow_id=IdentityRecoveryFlowId(UUID(int=99)) if scope == "flow" else EVENT.flow_id,
        subject=IdentitySubject("bob") if scope == "subject" else EVENT.identity.subject,
    )
    with pytest.raises(RuntimeError):
        await scenario.service.record_cleanup(
            event=EVENT, hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED
        )
    assert scenario.events == ["begin", "facts", "load", "rollback"]


@pytest.mark.asyncio
async def test_confirmed_state_cannot_regress_and_error_text_is_application_owned() -> None:
    scenario = MockCompletionScenario()
    scenario.recoveries.recovery.record_kratos_cleanup(IdentityRecoveryCleanupState.CONFIRMED)
    with pytest.raises(ConflictError) as error:
        await scenario.service.record_cleanup(
            event=EVENT, kratos_outcome=IdentityRecoveryCleanupState.FAILED
        )
    assert str(error.value) == "The cleanup outcome conflicts with confirmed recovery progress."
    assert isinstance(error.value.__cause__, IdentityRecoveryTransitionError)
    assert scenario.events[-1] == "rollback"
    assert scenario.recoveries.saved == []


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["facts", "load", "save", "commit"])
async def test_dependency_failures_propagate_without_a_success_result(
    stage: Literal["facts", "load", "save", "commit"],
) -> None:
    scenario = MockCompletionScenario()
    failure = DependencyUnavailableError("Simulated dependency failure.")
    if stage == "facts":
        scenario.facts.error = failure
    elif stage == "load":
        scenario.recoveries.get_error = failure
    elif stage == "save":
        scenario.recoveries.save_error = failure
    else:
        scenario.transactions.commit_error = failure
    with pytest.raises(DependencyUnavailableError) as error:
        await scenario.service.record_cleanup(
            event=EVENT, hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED
        )
    assert error.value is failure
    assert scenario.events[-1] == ("commit-failed" if stage == "commit" else "rollback")


@pytest.mark.asyncio
async def test_missing_durable_proof_cannot_release_a_recovery() -> None:
    scenario = MockCompletionScenario()
    with pytest.raises(ConflictError):
        await scenario.service.reconcile_proof(operation_id=OPERATION)
    assert scenario.recoveries.saved == []
    assert scenario.proofs.checked == []


@pytest.mark.asyncio
async def test_missing_credential_state_cannot_release_even_with_provider_confirmations() -> None:
    scenario = MockCompletionScenario()
    scenario.facts.facts = replace(scenario.facts.facts, credential_version=None)
    with pytest.raises(DependencyUnavailableError):
        await scenario.service.record_cleanup(
            event=EVENT,
            kratos_outcome=IdentityRecoveryCleanupState.CONFIRMED,
            hydra_outcome=IdentityRecoveryCleanupState.CONFIRMED,
        )
    assert scenario.recoveries.saved == []
