"""Exercise accounting decisions with transactional in-memory collaborators.

These controlled observations establish no provider evidence, SQL locks or real
session persistence. PostgreSQL reopened-session qualification remains separate.
"""

import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal, override
from uuid import UUID

import pytest
from tests.support.authentication_evidence import MockAuthenticationEvidence

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.admitted_work_authority_dto import (
    AdmittedWorkAuthorityDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.dtos.project_action_authorization_request_dto import (
    ProjectActionAuthorizationRequestDTO,
)
from inframeld_backend.access.application.protocols.admitted_work_authorizer import (
    AdmittedWorkAuthorizer,
)
from inframeld_backend.access.application.protocols.project_budget_authorizer import (
    ProjectBudgetAuthorizer,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.dtos.job_snapshot_dto import JobSnapshotDTO
from inframeld_backend.shared.application.dtos.product_job_binding_dto import ProductJobBindingDTO
from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_result_dto import (
    ProjectSpendingPolicyResultDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_context_dto import (
    SpendingCallContextDTO,
)
from inframeld_backend.shared.application.dtos.spending_call_record_dto import SpendingCallRecordDTO
from inframeld_backend.shared.application.dtos.spending_evidence_resolution_dto import (
    SpendingEvidenceResolutionDTO,
)
from inframeld_backend.shared.application.dtos.spending_observation_dto import (
    SpendingObservationDTO,
)
from inframeld_backend.shared.application.dtos.spending_projection_dto import SpendingProjectionDTO
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_totals_dto import SpendingTotalsDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO
from inframeld_backend.shared.application.enums.spending_call_state import SpendingCallState
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    ResourceNotFoundError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.job_errors import (
    JobFenceLostError,
    JobStoppedError,
)
from inframeld_backend.shared.application.errors.spending_errors import (
    IncompleteSpendingFactsError,
    SpendingLimitExceededError,
)
from inframeld_backend.shared.application.protocols.job_ownership import JobOwnership
from inframeld_backend.shared.application.protocols.spending_ledger_reader import (
    SpendingLedgerReader,
)
from inframeld_backend.shared.application.protocols.spending_ledger_writer import (
    SpendingLedgerWriter,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.services.spending_accounting_service import (
    SpendingAccountingService,
)
from inframeld_backend.shared.application.value_objects.job_fence import JobFence
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.application.value_objects.model_call_id import ModelCallId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_id import RequestId
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount

NOW = datetime(2026, 11, 1, tzinfo=UTC)
ORG = OrganizationId(UUID(int=3))
PROJECT = ProjectId(UUID(int=2))
ACTOR = PrincipalId(UUID(int=1))
ACCESS = AccessContextDTO(ACTOR, MockAuthenticationEvidence.browser())


def money(value: str) -> UsdAmount:
    return UsdAmount(Decimal(value))


def call_context(number: int = 1, *, attempt: int = 1) -> SpendingCallContextDTO:
    evidence = MockAuthenticationEvidence.human_oauth()
    authority = AdmittedWorkAuthorityDTO(
        ACTOR,
        PrincipalKind.HUMAN,
        evidence.installation_id,
        ORG,
        PROJECT,
        ActionId("build"),
        evidence,
    )
    operation = OperationId("original-job-operation")
    binding = ProductJobBindingDTO(operation, RequestId(UUID(int=5)), authority)
    context = JobAttemptContextDTO(
        JobId(UUID(int=6)),
        binding,
        JobPayload("fixture.accounting", 1, b""),
        attempt,
        JobFence(UUID(int=10 + attempt)),
        NOW + timedelta(hours=1),
        b"",
    )
    return SpendingCallContextDTO(
        ModelCallId(UUID(int=number)),
        operation,
        authority,
        context,
        RequestFingerprint(bytes([number]) * 32),
    )


def price_basis(amount: str = "0.1") -> CapturedSpendingBasisDTO:
    return CapturedSpendingBasisDTO(
        "basis",
        "fixture-pricing",
        "v1",
        NOW,
        (SpendingRateDTO("input", "unit", Decimal(amount)),),
        (SpendingUsageDTO("input", "unit", Decimal("1")),),
    )


def observation(
    call: SpendingCallContextDTO,
    *,
    number: int = 1,
    kind: Literal["usage", "charge", "not_sent", "not_billed", "uncertain"] = "charge",
    charge: str | None = "0.08",
) -> SpendingObservationDTO:
    return SpendingObservationDTO(
        UUID(int=100 + number),
        call.call_id,
        kind,
        NOW,
        "fixture-call-bound-evidence",
        charge=Decimal(charge) if charge is not None else None,
    )


@dataclass
class LedgerMemoryDTO:
    policy: ProjectSpendingPolicyDTO
    calls: dict[ModelCallId, SpendingCallRecordDTO] = field(
        default_factory=lambda: dict[ModelCallId, SpendingCallRecordDTO]()
    )
    evidence: dict[
        tuple[ModelCallId, UUID], tuple[SpendingObservationDTO, SpendingCallRecordDTO | None]
    ] = field(
        default_factory=lambda: dict[
            tuple[ModelCallId, UUID], tuple[SpendingObservationDTO, SpendingCallRecordDTO | None]
        ]()
    )
    operations: dict[OperationId, tuple[JobId, AdmittedWorkAuthorityDTO, UsdAmount | None]] = field(
        default_factory=lambda: dict[
            OperationId, tuple[JobId, AdmittedWorkAuthorityDTO, UsdAmount | None]
        ]()
    )
    results: dict[OperationId, tuple[ProjectSpendingPolicyDTO, PrincipalId, bool]] = field(
        default_factory=lambda: dict[
            OperationId, tuple[ProjectSpendingPolicyDTO, PrincipalId, bool]
        ]()
    )
    audits: list[str] = field(default_factory=lambda: list[str]())
    resolutions: dict[tuple[ModelCallId, UUID], SpendingEvidenceResolutionDTO] = field(
        default_factory=lambda: dict[tuple[ModelCallId, UUID], SpendingEvidenceResolutionDTO]()
    )

    pending_markers: set[tuple[ModelCallId, UUID]] = field(
        default_factory=lambda: set[tuple[ModelCallId, UUID]]()
    )


class MockLedger(SpendingLedgerReader, SpendingLedgerWriter):
    def __init__(self) -> None:
        self.state = LedgerMemoryDTO(ProjectSpendingPolicyDTO(ORG, PROJECT, 0, money("1"), NOW))
        self.events: list[str] = []
        self.now = NOW
        self.observation_failure: BaseException | None = None
        self.resolution_failure: BaseException | None = None
        self.audit_failure: BaseException | None = None
        self.returned_policy: ProjectSpendingPolicyDTO | None = None
        self.returned_call: SpendingCallRecordDTO | None = None
        self.returned_projection: SpendingProjectionDTO | None = None
        self.returned_policy_result: ProjectSpendingPolicyResultDTO | None = None
        self.returned_resolution: SpendingEvidenceResolutionDTO | None = None
        self.rebound_on_lock: SpendingCallRecordDTO | None = None

    @override
    async def ensure_project_account(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> None:
        self.events.append("ensure")
        assert (organization_id, project_id) == (ORG, PROJECT)

    @override
    async def lock_project_policy(
        self, *, organization_id: OrganizationId, project_id: ProjectId
    ) -> ProjectSpendingPolicyDTO:
        self.events.append("account")
        assert (organization_id, project_id) == (ORG, PROJECT)
        if self.rebound_on_lock is not None:
            self.state.calls[self.rebound_on_lock.call_id] = self.rebound_on_lock
        if self.returned_policy is not None:
            return self.returned_policy
        return replace(self.state.policy, observed_at=self.now)

    @override
    async def ensure_operation(
        self, *, call: SpendingCallContextDTO, operation_limit: UsdAmount | None
    ) -> None:
        self.events.append("operation")
        binding = (call.attempt.job_id, call.authority, operation_limit)
        original = self.state.operations.setdefault(call.operation_id, binding)
        if original != binding:
            raise ConflictError("Original operation binding changed.")

    @override
    async def find_call(
        self, *, organization_id: OrganizationId, project_id: ProjectId, call_id: ModelCallId
    ) -> SpendingCallRecordDTO | None:
        self.events.append("find")
        if self.returned_call is not None:
            return self.returned_call
        record = self.state.calls.get(call_id)
        if record is None or (record.authority.organization_id, record.authority.project_id) != (
            organization_id,
            project_id,
        ):
            return None
        return record

    @override
    async def insert_call(self, record: SpendingCallRecordDTO) -> None:
        if record.call_id in self.state.calls:
            raise ConflictError()
        self.state.calls[record.call_id] = record

    @override
    async def save_call(self, record: SpendingCallRecordDTO, *, expected_revision: int) -> None:
        original = self.state.calls[record.call_id]
        if original.revision != expected_revision:
            raise StaleRevisionError()
        self.state.calls[record.call_id] = record

    def _totals(self, records: list[SpendingCallRecordDTO]) -> SpendingTotalsDTO:
        settled = Decimal("0")
        held = Decimal("0")
        unknown = 0
        for record in records:
            pending = any(
                key[0] == record.call_id and key not in self.state.resolutions
                for key in self.state.pending_markers
            )
            if record.state is SpendingCallState.SETTLED:
                assert record.settled_amount is not None
                settled += record.settled_amount.value
            elif record.state is not SpendingCallState.RELEASED:
                if record.hold_amount is None:
                    pending = True
                else:
                    held += record.hold_amount.value
            unknown += int(pending)
        return SpendingTotalsDTO(UsdAmount(settled), UsdAmount(held), unknown)

    @override
    async def project_totals(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        period: SpendingPeriod,
        exclude_call_id: ModelCallId | None = None,
    ) -> SpendingTotalsDTO:
        return self._totals(
            [
                r
                for r in self.state.calls.values()
                if r.authority.organization_id == organization_id
                and r.authority.project_id == project_id
                and r.period == period
                and r.call_id != exclude_call_id
            ]
        )

    @override
    async def operation_totals(
        self, *, record: SpendingCallRecordDTO, exclude_call_id: ModelCallId | None = None
    ) -> SpendingTotalsDTO:
        return self._totals(
            [
                r
                for r in self.state.calls.values()
                if r.operation_id == record.operation_id and r.call_id != exclude_call_id
            ]
        )

    @override
    async def observation(
        self, *, record: SpendingCallRecordDTO, evidence_id: UUID
    ) -> tuple[SpendingObservationDTO, SpendingCallRecordDTO | None, bool] | None:
        key = (record.call_id, evidence_id)
        retained = self.state.evidence.get(key)
        if retained is None:
            return None
        return (
            retained[0],
            retained[1],
            key in self.state.pending_markers and key not in self.state.resolutions,
        )

    @override
    async def resolution(
        self, *, record: SpendingCallRecordDTO, pending_evidence_id: UUID
    ) -> SpendingEvidenceResolutionDTO | None:
        self.events.append("resolution-read")
        if self.returned_resolution is not None:
            return self.returned_resolution
        return self.state.resolutions.get((record.call_id, pending_evidence_id))

    @override
    async def record_observation(
        self,
        *,
        record: SpendingCallRecordDTO,
        observation: SpendingObservationDTO,
        applied_result: SpendingCallRecordDTO | None,
    ) -> None:
        self.events.append("evidence-write")
        if self.observation_failure is not None:
            raise self.observation_failure
        key = (record.call_id, observation.evidence_id)
        previous = self.state.evidence.get(key)
        if previous is not None and previous[0] != observation:
            raise ConflictError("Evidence identity changed meaning.")
        if previous is None and applied_result is None:
            self.state.pending_markers.add(key)
        self.state.evidence.setdefault(key, (observation, applied_result))

    @override
    async def mark_observation_applied(
        self, *, record: SpendingCallRecordDTO, evidence_id: UUID, result: SpendingCallRecordDTO
    ) -> None:
        original, _ = self.state.evidence[(record.call_id, evidence_id)]
        self.state.evidence[(record.call_id, evidence_id)] = (original, result)

    @override
    async def record_resolution(
        self, *, record: SpendingCallRecordDTO, resolution: SpendingEvidenceResolutionDTO
    ) -> None:
        if self.resolution_failure is not None:
            raise self.resolution_failure
        key = (record.call_id, resolution.pending_evidence_id)
        if key in self.state.resolutions:
            raise ConflictError("Pending evidence already has a resolution.")
        self.state.resolutions[key] = resolution

    @override
    async def save_correction_audit(
        self,
        *,
        actor_id: PrincipalId,
        resolution: SpendingEvidenceResolutionDTO,
        previous_revision: int,
    ) -> None:
        if self.audit_failure is not None:
            raise self.audit_failure
        self.state.audits.append("correction")

    @override
    async def change_policy(
        self,
        *,
        policy: ProjectSpendingPolicyDTO,
        expected_revision: int,
        actor_id: PrincipalId,
        operation_id: OperationId,
    ) -> None:
        if self.state.policy.revision != expected_revision:
            raise StaleRevisionError()
        self.state.policy = policy
        self.state.audits.append("policy")

    @override
    async def save_policy_result(
        self,
        *,
        policy: ProjectSpendingPolicyDTO,
        actor_id: PrincipalId,
        operation_id: OperationId,
        changed: bool,
    ) -> None:
        self.state.results[operation_id] = (policy, actor_id, changed)

    @override
    async def policy_result(
        self,
        *,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_id: PrincipalId,
        completion: CompletedSynchronousOperationDTO,
    ) -> ProjectSpendingPolicyResultDTO:
        if self.returned_policy_result is not None:
            return self.returned_policy_result
        policy, owner, changed = self.state.results[completion.operation_id]
        if owner != actor_id or (policy.organization_id, policy.project_id) != (
            organization_id,
            project_id,
        ):
            raise ResourceNotFoundError()
        return ProjectSpendingPolicyResultDTO(policy, completion, changed)

    @override
    async def project_projection(
        self, *, organization_id: OrganizationId, project_id: ProjectId, period: SpendingPeriod
    ) -> SpendingProjectionDTO:
        self.events.append("projection")
        if self.returned_projection is not None:
            return self.returned_projection
        totals = await self.project_totals(
            organization_id=organization_id, project_id=project_id, period=period
        )
        limit = self.state.policy.monthly_limit
        remaining = (
            None
            if limit is None or totals.unquantified_holds
            else UsdAmount(limit.value - totals.settled.value - totals.held.value)
        )
        return SpendingProjectionDTO(self.state.policy, period, totals, remaining)


class MockTransactions(TransactionManager):
    def __init__(self, ledger: MockLedger) -> None:
        self.ledger = ledger

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        previous = deepcopy(self.ledger.state)
        committed = False
        self.ledger.events.append("begin")
        try:
            yield
            committed = True
        finally:
            if committed:
                self.ledger.events.append("commit")
            else:
                self.ledger.state = previous
                self.ledger.events.append("rollback")


class MockWorkAuthorizer(AdmittedWorkAuthorizer):
    def __init__(self, ledger: MockLedger) -> None:
        self.ledger = ledger
        self.failure: BaseException | None = None

    @override
    async def require_current(self, authority: AdmittedWorkAuthorityDTO) -> None:
        self.ledger.events.append("authorize")
        if self.failure is not None:
            raise self.failure


class MockOwnership(JobOwnership):
    def __init__(self, ledger: MockLedger) -> None:
        self.ledger = ledger
        self.failure: BaseException | None = None
        self.cancel_requested = False

    @override
    async def require_current(self, context: JobAttemptContextDTO) -> JobSnapshotDTO:
        self.ledger.events.append("ownership")
        if self.failure is not None:
            raise self.failure
        return JobSnapshotDTO(
            context.job_id,
            context.binding,
            context.payload,
            JobStatus.RUNNING,
            NOW,
            NOW + timedelta(days=1),
            NOW,
            NOW,
            context.attempt,
            context.work_deadline,
            context.fence,
            NOW + timedelta(seconds=30),
            self.cancel_requested,
            None,
            None,
            context.checkpoint,
        )


class MockBudgetAuthorizer(ProjectBudgetAuthorizer):
    def __init__(self, ledger: MockLedger) -> None:
        self.ledger = ledger
        self.failure: BaseException | None = None
        self.scope = ProjectActionAuthorizationDTO(ORG, PROJECT)
        self.actions: list[str] = []

    @override
    async def require_authorization(
        self, *, access: AccessContextDTO, request: ProjectActionAuthorizationRequestDTO
    ) -> ProjectActionAuthorizationDTO:
        self.ledger.events.append("budget-authorize")
        self.actions.append(request.action_id.value)
        if self.failure is not None:
            raise self.failure
        return self.scope


def accountant(
    ledger: MockLedger | None = None,
) -> tuple[
    SpendingAccountingService, MockLedger, MockOwnership, MockWorkAuthorizer, MockBudgetAuthorizer
]:
    ledger = ledger if ledger is not None else MockLedger()
    ownership = MockOwnership(ledger)
    authorizer = MockWorkAuthorizer(ledger)
    budget = MockBudgetAuthorizer(ledger)
    service = SpendingAccountingService(
        transactions=MockTransactions(ledger),
        authorizer=authorizer,
        ownership=ownership,
        reader=ledger,
        writer=ledger,
        budget_authorizer=budget,
    )
    return service, ledger, ownership, authorizer, budget


@pytest.mark.asyncio
async def test_reservation_uses_authorization_ownership_then_accounting_and_original_operation() -> (
    None
):
    service, ledger, _, _, _ = accountant()
    call = call_context()

    result = await service.reserve(call=call, basis=price_basis(), operation_limit=money("1"))

    assert isinstance(call.attempt.binding, ProductJobBindingDTO)
    assert result.record.operation_id == call.attempt.binding.operation_id
    assert result.record.job_id == call.attempt.job_id
    assert result.record.reserved_amount == money("0.1")
    assert result.record.period == SpendingPeriod(2026, 11)
    assert (
        ledger.events.index("authorize")
        < ledger.events.index("ownership")
        < ledger.events.index("ensure")
        < ledger.events.index("account")
    )
    assert ledger.events[-1] == "commit"


@pytest.mark.asyncio
async def test_below_quantum_rate_is_rounded_only_after_exact_multiplication() -> None:
    service, _, _, _, _ = accountant()
    basis = CapturedSpendingBasisDTO(
        "tiny",
        "fixture",
        "v1",
        NOW,
        (SpendingRateDTO("input", "unit", Decimal("0.000000000000001")),),
        (SpendingUsageDTO("input", "unit", Decimal("1000")),),
    )

    result = await service.reserve(call=call_context(), basis=basis, operation_limit=money("1"))

    assert result.record.reserved_amount == money("0.000000000001")
    assert result.record.basis == basis


@pytest.mark.asyncio
async def test_held_allowance_prevents_another_call_from_spending_it() -> None:
    service, ledger, _, _, _ = accountant()
    await service.reserve(call=call_context(), basis=price_basis("0.7"), operation_limit=None)

    with pytest.raises(SpendingLimitExceededError):
        await service.reserve(call=call_context(2), basis=price_basis("0.7"), operation_limit=None)

    assert len(ledger.state.calls) == 1


@pytest.mark.asyncio
async def test_same_call_recovers_original_record_and_changed_meaning_conflicts() -> None:
    service, ledger, _, _, _ = accountant()
    call = call_context()
    first = await service.reserve(call=call, basis=price_basis(), operation_limit=money("1"))
    replay = await service.reserve(call=call, basis=price_basis(), operation_limit=money("1"))

    assert replay.recovered and replay.record == first.record
    with pytest.raises(ConflictError):
        await service.reserve(call=call, basis=price_basis("0.2"), operation_limit=money("1"))
    assert len(ledger.state.calls) == 1


def test_attempt_is_mandatory_and_original_operation_cannot_be_rebound() -> None:
    call = call_context()
    with pytest.raises(TypeError):
        replace(call, attempt=None)
    with pytest.raises(ValueError):
        replace(call, operation_id=OperationId("another-operation"))


@pytest.mark.asyncio
async def test_actual_ownership_failure_prevents_new_reservation() -> None:
    service, ledger, ownership, _, _ = accountant()
    ownership.failure = JobFenceLostError()

    with pytest.raises(JobFenceLostError):
        await service.reserve(call=call_context(), basis=price_basis(), operation_limit=None)

    assert not ledger.state.calls
    assert "ensure" not in ledger.events


@pytest.mark.asyncio
async def test_capped_unknown_price_is_rejected_without_treating_it_as_zero() -> None:
    service, ledger, _, _, _ = accountant()

    with pytest.raises(IncompleteSpendingFactsError):
        await service.reserve(call=call_context(), basis=None, operation_limit=None)

    assert not ledger.state.calls


@pytest.mark.asyncio
async def test_unknown_original_obligation_blocks_new_cap_in_its_month_but_not_a_new_project_month() -> (
    None
):
    service, ledger, _, _, _ = accountant()
    ledger.state.policy = replace(ledger.state.policy, monthly_limit=None)
    call = call_context()
    await service.reserve(call=call, basis=None, operation_limit=None)
    await service.record_observation(
        call=call,
        observation=observation(call, kind="uncertain", charge=None),
        expected_call_revision=0,
    )
    ledger.state.policy = replace(ledger.state.policy, monthly_limit=money("1"), revision=1)

    with pytest.raises(IncompleteSpendingFactsError):
        await service.reserve(call=call_context(2), basis=price_basis(), operation_limit=None)

    ledger.now = datetime(2026, 12, 1, tzinfo=UTC)
    result = await service.reserve(call=call_context(2), basis=price_basis(), operation_limit=None)
    assert result.record.period == SpendingPeriod(2026, 12)
    assert ledger.state.calls[call.call_id].period == SpendingPeriod(2026, 11)
    assert ledger.state.calls[call.call_id].hold_amount is None


@pytest.mark.asyncio
async def test_operation_limit_survives_month_and_attempt_changes() -> None:
    service, ledger, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis("0.6"), operation_limit=money("1"))
    await service.record_observation(
        call=call, observation=observation(call, charge="0.6"), expected_call_revision=0
    )
    ledger.now = datetime(2026, 12, 1, tzinfo=UTC)

    with pytest.raises(SpendingLimitExceededError):
        await service.reserve(
            call=call_context(2, attempt=2), basis=price_basis("0.6"), operation_limit=money("1")
        )
    with pytest.raises(ConflictError):
        await service.reserve(
            call=call_context(2, attempt=2), basis=price_basis(), operation_limit=None
        )


@pytest.mark.asyncio
async def test_policy_change_before_accounting_approval_denies_without_releasing_unproven_hold() -> (
    None
):
    service, ledger, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis("0.7"), operation_limit=None)
    ledger.state.policy = replace(ledger.state.policy, monthly_limit=money("0.5"), revision=1)

    with pytest.raises(SpendingLimitExceededError):
        await service.approve_accounting(call=call, expected_call_revision=0)

    assert ledger.state.calls[call.call_id].state is SpendingCallState.RESERVED
    assert ledger.state.calls[call.call_id].hold_amount == money("0.7")


@pytest.mark.asyncio
async def test_recovered_accounting_approval_does_not_release_or_reapprove_after_policy_edit() -> (
    None
):
    service, ledger, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    approved = await service.approve_accounting(call=call, expected_call_revision=0)
    ledger.state.policy = replace(ledger.state.policy, monthly_limit=money("0"), revision=1)

    recovered = await service.approve_accounting(call=call, expected_call_revision=0)

    assert recovered.recovered and recovered.record == approved.record
    assert recovered.record.approved_policy_revision == 0
    assert recovered.record.hold_amount == money("0.1")


@pytest.mark.asyncio
async def test_known_charge_settles_once_and_records_an_overage_honestly() -> None:
    service, ledger, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=money("0.1"))
    evidence = observation(call, charge="0.15")
    first = await service.record_observation(
        call=call, observation=evidence, expected_call_revision=0
    )
    duplicate = await service.record_observation(
        call=call, observation=evidence, expected_call_revision=0
    )

    assert first.record.state is SpendingCallState.SETTLED
    assert first.record.settled_amount == money("0.15")
    assert first.record.hold_amount == money("0")
    assert duplicate.recovered and duplicate.record == first.record
    assert len(ledger.state.evidence) == 1


@pytest.mark.asyncio
async def test_evidence_identity_cannot_change_meaning() -> None:
    service, ledger, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    evidence = observation(call)
    await service.record_observation(call=call, observation=evidence, expected_call_revision=0)

    with pytest.raises(ConflictError):
        await service.record_observation(
            call=call,
            observation=replace(evidence, charge=Decimal("0.2")),
            expected_call_revision=1,
        )

    assert ledger.state.calls[call.call_id].settled_amount == money("0.08")


@pytest.mark.asyncio
async def test_missing_usage_keeps_the_original_hold_and_cannot_approve_redispatch() -> None:
    service, ledger, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    result = await service.record_observation(
        call=call,
        observation=observation(call, kind="uncertain", charge=None),
        expected_call_revision=0,
    )

    assert result.record.state is SpendingCallState.UNRESOLVED
    assert result.record.hold_amount == money("0.1")
    with pytest.raises(ConflictError):
        await service.approve_accounting(call=call, expected_call_revision=1)
    assert ledger.state.calls[call.call_id] == result.record


@pytest.mark.asyncio
async def test_current_call_bound_not_sent_evidence_can_release_unused_hold() -> None:
    service, _, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)

    result = await service.record_observation(
        call=call,
        observation=observation(call, kind="not_sent", charge=None),
        expected_call_revision=0,
    )

    assert result.record.state is SpendingCallState.RELEASED
    assert result.record.hold_amount == money("0")


@pytest.mark.asyncio
async def test_stale_fence_retains_pending_evidence_through_normal_transaction_return() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    original = await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    evidence = observation(call, kind="not_billed", charge=None)

    result = await service.record_observation(
        call=call, observation=evidence, expected_call_revision=0
    )

    assert result.pending
    assert ledger.state.calls[call.call_id] == replace(original.record, revision=1)
    assert ledger.state.evidence[(call.call_id, evidence.evidence_id)] == (evidence, None)
    assert ledger.events[-1] == "commit"
    reopened_service, reopened, _, _, _ = accountant(ledger)
    assert reopened is ledger
    reconciled = await reopened_service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=evidence.evidence_id,
        authoritative_evidence_id=evidence.evidence_id,
        expected_call_revision=result.record.revision,
    )
    assert reconciled.record.state is SpendingCallState.RELEASED
    assert reopened.state.audits == ["correction"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [AccessDeniedError(), DependencyUnavailableError(), asyncio.CancelledError()]
)
async def test_denial_dependency_and_cancellation_do_not_become_pending_evidence(
    failure: BaseException,
) -> None:
    service, ledger, ownership, authorizer, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    if isinstance(failure, AccessDeniedError):
        authorizer.failure = failure
    else:
        ownership.failure = failure

    with pytest.raises(type(failure)):
        await service.record_observation(
            call=call, observation=observation(call), expected_call_revision=0
        )

    assert not ledger.state.evidence
    assert ledger.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_pending_evidence_write_failure_rolls_back_instead_of_claiming_retention() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    ledger.observation_failure = DependencyUnavailableError()

    with pytest.raises(DependencyUnavailableError):
        await service.record_observation(
            call=call, observation=observation(call), expected_call_revision=0
        )

    assert not ledger.state.evidence
    assert ledger.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_stale_fence_cannot_admit_evidence_for_a_missing_or_rebound_call() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    ownership.failure = JobFenceLostError()

    with pytest.raises(ResourceNotFoundError):
        await service.record_observation(
            call=call, observation=observation(call), expected_call_revision=0
        )

    ownership.failure = None
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ledger.state.calls[call.call_id] = replace(
        ledger.state.calls[call.call_id], job_id=JobId(UUID(int=99))
    )
    ownership.failure = JobFenceLostError()
    with pytest.raises(ConflictError):
        await service.record_observation(
            call=call, observation=observation(call), expected_call_revision=0
        )
    assert not ledger.state.evidence


@pytest.mark.asyncio
async def test_human_correction_requires_current_management_before_evidence_lookup() -> None:
    service, ledger, ownership, _, budget = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    evidence = observation(call)
    await service.record_observation(call=call, observation=evidence, expected_call_revision=0)
    budget.failure = AccessDeniedError()

    with pytest.raises(AccessDeniedError):
        await service.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=evidence.evidence_id,
            authoritative_evidence_id=evidence.evidence_id,
            expected_call_revision=0,
        )

    assert budget.actions == ["manage-budget"]
    assert ledger.state.evidence[(call.call_id, evidence.evidence_id)][1] is None


@pytest.mark.asyncio
async def test_pending_evidence_for_the_reserved_call_blocks_capped_accounting_approval() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    original = await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    await service.record_observation(
        call=call, observation=observation(call), expected_call_revision=0
    )
    ownership.failure = None
    with pytest.raises(IncompleteSpendingFactsError):
        await service.approve_accounting(call=call, expected_call_revision=1)
    assert ledger.state.calls[call.call_id] == replace(original.record, revision=1)


@pytest.mark.asyncio
async def test_unknown_usage_categories_preserve_an_unquantified_obligation() -> None:
    service, ledger, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    evidence = SpendingObservationDTO(
        UUID(int=701),
        call.call_id,
        "usage",
        NOW,
        "fixture-unknown-category",
        usage=(SpendingUsageDTO("unsupported", "unit", Decimal("1")),),
    )
    result = await service.record_observation(
        call=call, observation=evidence, expected_call_revision=0
    )
    assert result.record.reserved_amount == money("0.1")
    assert result.record.hold_amount is None
    with pytest.raises(IncompleteSpendingFactsError):
        await service.reserve(call=call_context(2), basis=price_basis(), operation_limit=None)
    assert len(ledger.state.calls) == 1


@pytest.mark.asyncio
async def test_duplicate_evidence_recovers_its_retained_receipt_after_a_human_correction() -> None:
    service, ledger, _, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    first = observation(call)
    original = await service.record_observation(
        call=call, observation=first, expected_call_revision=0
    )
    correction = observation(call, number=2, charge="0.15")
    pending = await service.record_observation(
        call=call, observation=correction, expected_call_revision=1
    )
    assert pending.pending and ledger.state.calls[call.call_id] == replace(
        original.record, revision=2
    )
    corrected = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=correction.evidence_id,
        authoritative_evidence_id=correction.evidence_id,
        expected_call_revision=pending.record.revision,
    )
    duplicate = await service.record_observation(
        call=call, observation=first, expected_call_revision=0
    )
    assert duplicate.recovered and duplicate.record == original.record
    assert ledger.state.calls[call.call_id] == corrected.record
    repeated_correction = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=correction.evidence_id,
        authoritative_evidence_id=correction.evidence_id,
        expected_call_revision=pending.record.revision,
    )
    assert repeated_correction.recovered and repeated_correction.record == corrected.record
    assert ledger.state.audits == ["correction"]


@pytest.mark.asyncio
async def test_stale_revision_rejects_new_evidence_without_partial_retention() -> None:
    service, ledger, _, _, _ = accountant()
    call = call_context()
    original = await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    with pytest.raises(StaleRevisionError):
        await service.record_observation(
            call=call, observation=observation(call), expected_call_revision=3
        )
    assert ledger.state.calls[call.call_id] == original.record and not ledger.state.evidence


@pytest.mark.asyncio
async def test_cancellation_stops_new_work_but_does_not_discard_charge_evidence() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.cancel_requested = True
    with pytest.raises(JobStoppedError):
        await service.reserve(call=call_context(2), basis=price_basis(), operation_limit=None)
    with pytest.raises(JobStoppedError):
        await service.approve_accounting(call=call, expected_call_revision=0)
    result = await service.record_observation(
        call=call, observation=observation(call), expected_call_revision=0
    )
    assert result.record.settled_amount == money("0.08")
    assert len(ledger.state.calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["uncertain", "usage"])
async def test_human_review_cannot_resolve_pending_evidence_without_accounting_facts(
    kind: str,
) -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    original = await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    evidence = (
        observation(call, kind="uncertain", charge=None)
        if kind == "uncertain"
        else SpendingObservationDTO(
            UUID(int=702),
            call.call_id,
            "usage",
            NOW,
            "fixture-unbounded",
            usage=(SpendingUsageDTO("unsupported", "unit", Decimal("1")),),
        )
    )
    await service.record_observation(call=call, observation=evidence, expected_call_revision=0)
    with pytest.raises(IncompleteSpendingFactsError):
        await service.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=evidence.evidence_id,
            authoritative_evidence_id=evidence.evidence_id,
            expected_call_revision=1,
        )
    assert ledger.state.calls[call.call_id] == replace(original.record, revision=1)
    assert ledger.state.evidence[(call.call_id, evidence.evidence_id)] == (evidence, None)
    assert not ledger.state.audits


@pytest.mark.asyncio
async def test_review_stale_pending_is_coordinated_and_advances_only_call_revision() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    original = await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ledger.events.clear()
    ownership.failure = JobFenceLostError()
    result = await service.record_observation(
        call=call, observation=observation(call), expected_call_revision=0
    )
    assert result.pending and result.record == replace(original.record, revision=1)
    assert (
        ledger.events.index("authorize")
        < ledger.events.index("ownership")
        < ledger.events.index("account")
    )
    assert (
        ledger.events.index("account")
        < max(i for i, event in enumerate(ledger.events) if event == "find")
        < ledger.events.index("evidence-write")
    )
    with pytest.raises(StaleRevisionError):
        await service.record_observation(
            call=call, observation=observation(call, number=2), expected_call_revision=0
        )
    assert ledger.state.calls[call.call_id] == result.record
    assert len(ledger.state.pending_markers) == 1


@pytest.mark.asyncio
async def test_review_stale_pending_rereads_original_binding_after_coordination() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    original = await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    ledger.rebound_on_lock = replace(original.record, job_id=JobId(UUID(int=99)))
    with pytest.raises(ConflictError):
        await service.record_observation(
            call=call, observation=observation(call), expected_call_revision=0
        )
    assert not ledger.state.evidence


async def pending_then_applied_charge() -> tuple[
    SpendingAccountingService,
    MockLedger,
    MockOwnership,
    SpendingCallContextDTO,
    SpendingObservationDTO,
    SpendingObservationDTO,
    SpendingCallRecordDTO,
]:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    pending = observation(call, kind="uncertain", charge=None)
    retained = await service.record_observation(
        call=call, observation=pending, expected_call_revision=0
    )
    ownership.failure = None
    proof = observation(call, number=2)
    applied = await service.record_observation(
        call=call, observation=proof, expected_call_revision=retained.record.revision
    )
    return service, ledger, ownership, call, pending, proof, applied.record


@pytest.mark.asyncio
async def test_review_resolution_replays_its_own_receipt_and_preserves_other_pending_items() -> (
    None
):
    service, ledger, ownership, call, pending, proof, applied = await pending_then_applied_charge()
    resolved = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=pending.evidence_id,
        authoritative_evidence_id=proof.evidence_id,
        expected_call_revision=applied.revision,
    )
    assert resolved.record == replace(applied, revision=applied.revision + 1)
    assert ledger.state.evidence[(call.call_id, pending.evidence_id)] == (pending, None)
    assert ledger.state.evidence[(call.call_id, proof.evidence_id)] == (proof, applied)
    assert ledger.state.resolutions[(call.call_id, pending.evidence_id)].result == resolved.record
    ownership.failure = JobFenceLostError()
    later_pending = observation(call, number=3, kind="uncertain", charge=None)
    retained = await service.record_observation(
        call=call, observation=later_pending, expected_call_revision=resolved.record.revision
    )
    ownership.failure = None
    later_proof = observation(call, number=4, charge="0.15")
    later = await service.record_observation(
        call=call, observation=later_proof, expected_call_revision=retained.record.revision
    )
    corrected = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=later_pending.evidence_id,
        authoritative_evidence_id=later_proof.evidence_id,
        expected_call_revision=later.record.revision,
    )
    assert corrected.record.settled_amount == money("0.15")
    replay = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=pending.evidence_id,
        authoritative_evidence_id=proof.evidence_id,
        expected_call_revision=applied.revision,
    )
    assert replay.recovered and replay.record == resolved.record
    assert ledger.state.calls[call.call_id] == corrected.record
    assert ledger.state.audits == ["correction", "correction"]
    old_financial = await service.record_observation(
        call=call, observation=proof, expected_call_revision=0
    )
    old_pending = await service.record_observation(
        call=call, observation=pending, expected_call_revision=0
    )
    assert old_financial.recovered and old_financial.record == applied
    assert (
        old_pending.recovered and not old_pending.pending and old_pending.record == resolved.record
    )
    ownership.failure = JobFenceLostError()
    new_pending = observation(call, number=5, kind="uncertain", charge=None)
    newest = await service.record_observation(
        call=call, observation=new_pending, expected_call_revision=corrected.record.revision
    )
    ownership.failure = None
    with pytest.raises(IncompleteSpendingFactsError):
        await service.reserve(call=call_context(2), basis=price_basis(), operation_limit=None)
    assert ledger.state.calls[call.call_id] == newest.record
    assert (call.call_id, new_pending.evidence_id) not in ledger.state.resolutions


@pytest.mark.asyncio
async def test_review_resolution_requires_selected_pending_status_and_current_revision() -> None:
    service, ledger, _, call, pending, proof, applied = await pending_then_applied_charge()
    with pytest.raises(StaleRevisionError):
        await service.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=pending.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=applied.revision + 1,
        )
    with pytest.raises(ConflictError):
        await service.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=proof.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=applied.revision,
        )
    assert ledger.state.calls[call.call_id] == applied and not ledger.state.resolutions


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["audit", "resolution"])
async def test_review_resolution_and_audit_failures_roll_back_processing(failure_at: str) -> None:
    service, ledger, _, call, pending, proof, applied = await pending_then_applied_charge()
    if failure_at == "audit":
        ledger.audit_failure = DependencyUnavailableError()
    else:
        ledger.resolution_failure = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await service.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=pending.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=applied.revision,
        )
    assert ledger.state.calls[call.call_id] == applied
    assert not ledger.state.resolutions and not ledger.state.audits
    assert ledger.state.evidence[(call.call_id, pending.evidence_id)] == (pending, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["organization", "project", "call"])
async def test_review_reconciliation_rejects_a_call_returned_in_another_scope(changed: str) -> None:
    service, ledger, _, call, pending, proof, applied = await pending_then_applied_charge()
    wrong = applied
    if changed == "organization":
        wrong = replace(
            applied,
            authority=replace(applied.authority, organization_id=OrganizationId(UUID(int=99))),
        )
    elif changed == "project":
        wrong = replace(
            applied, authority=replace(applied.authority, project_id=ProjectId(UUID(int=99)))
        )
    else:
        wrong = replace(applied, call_id=ModelCallId(UUID(int=99)))
    ledger.returned_call = wrong
    with pytest.raises(RuntimeError, match="scope"):
        await service.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=pending.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=applied.revision,
        )
    assert not ledger.state.resolutions and not ledger.state.audits


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["organization", "project", "call", "pending", "proof"])
async def test_review_reconciliation_rejects_a_misbound_resolution_receipt(changed: str) -> None:
    service, ledger, _, call, pending, proof, applied = await pending_then_applied_charge()
    receipt = SpendingEvidenceResolutionDTO(pending.evidence_id, proof.evidence_id, applied)
    if changed == "organization":
        receipt = replace(
            receipt,
            result=replace(
                applied,
                authority=replace(applied.authority, organization_id=OrganizationId(UUID(int=99))),
            ),
        )
    elif changed == "project":
        receipt = replace(
            receipt,
            result=replace(
                applied, authority=replace(applied.authority, project_id=ProjectId(UUID(int=99)))
            ),
        )
    elif changed == "call":
        receipt = replace(receipt, result=replace(applied, call_id=ModelCallId(UUID(int=99))))
    elif changed == "pending":
        receipt = replace(receipt, pending_evidence_id=UUID(int=99))
    else:
        receipt = replace(receipt, authoritative_evidence_id=UUID(int=99))
    ledger.returned_resolution = receipt
    with pytest.raises((RuntimeError, ConflictError), match="scope|binding"):
        await service.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=pending.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=applied.revision,
        )
    assert not ledger.state.audits


@pytest.mark.asyncio
async def test_resolution_replay_still_checks_current_management_and_proof_meaning() -> None:
    service, ledger, _, call, pending, proof, applied = await pending_then_applied_charge()
    await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=pending.evidence_id,
        authoritative_evidence_id=proof.evidence_id,
        expected_call_revision=applied.revision,
    )
    reopened, _, _, _, authorizer = accountant(ledger)
    ledger.events.clear()
    authorizer.failure = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await reopened.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=pending.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=applied.revision,
        )
    assert "resolution-read" not in ledger.events
    authorizer.failure = None
    with pytest.raises(ConflictError):
        await reopened.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=pending.evidence_id,
            authoritative_evidence_id=UUID(int=999),
            expected_call_revision=applied.revision,
        )
    assert ledger.state.audits == ["correction"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure_at", ["audit", "resolution"])
async def test_failed_self_resolution_rolls_back_a_new_financial_application(
    failure_at: str,
) -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    proof = observation(call, charge="0.15")
    pending = await service.record_observation(
        call=call, observation=proof, expected_call_revision=0
    )
    if failure_at == "audit":
        ledger.audit_failure = DependencyUnavailableError()
    else:
        ledger.resolution_failure = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await service.reconcile(
            access=ACCESS,
            project_id=PROJECT,
            call_id=call.call_id,
            pending_evidence_id=proof.evidence_id,
            authoritative_evidence_id=proof.evidence_id,
            expected_call_revision=pending.record.revision,
        )
    assert ledger.state.calls[call.call_id] == pending.record
    assert ledger.state.evidence[(call.call_id, proof.evidence_id)] == (proof, None)
    assert not ledger.state.resolutions and not ledger.state.audits


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["organization", "project"])
async def test_accounting_cannot_reserve_against_a_policy_returned_for_another_scope(
    changed: str,
) -> None:
    service, ledger, _, _, _ = accountant()
    ledger.returned_policy = (
        replace(ledger.state.policy, organization_id=OrganizationId(UUID(int=99)))
        if changed == "organization"
        else replace(ledger.state.policy, project_id=ProjectId(UUID(int=99)))
    )
    with pytest.raises(RuntimeError, match="scope"):
        await service.reserve(call=call_context(), basis=price_basis(), operation_limit=None)
    assert not ledger.state.operations and not ledger.state.calls


@pytest.mark.asyncio
async def test_applying_distinct_pending_proof_does_not_resolve_its_own_marker() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    pending = observation(call, kind="uncertain", charge=None)
    first = await service.record_observation(
        call=call, observation=pending, expected_call_revision=0
    )
    proof = observation(call, number=2, charge="0.15")
    second = await service.record_observation(
        call=call, observation=proof, expected_call_revision=first.record.revision
    )
    ownership.failure = None
    resolved = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=pending.evidence_id,
        authoritative_evidence_id=proof.evidence_id,
        expected_call_revision=second.record.revision,
    )
    assert resolved.record.settled_amount == money("0.15")
    totals = await ledger.project_totals(
        organization_id=ORG, project_id=PROJECT, period=resolved.record.period
    )
    assert totals.unquantified_holds == 1
    assert (call.call_id, proof.evidence_id) not in ledger.state.resolutions
    original_financial = ledger.state.evidence[(call.call_id, proof.evidence_id)]
    duplicate = await service.record_observation(
        call=call, observation=proof, expected_call_revision=0
    )
    assert duplicate.recovered and duplicate.pending and duplicate.record == resolved.record
    finished = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=proof.evidence_id,
        authoritative_evidence_id=proof.evidence_id,
        expected_call_revision=resolved.record.revision,
    )
    assert finished.record == replace(resolved.record, revision=resolved.record.revision + 1)
    assert ledger.state.evidence[(call.call_id, proof.evidence_id)] == original_financial
    assert ledger.state.audits == ["correction", "correction"]
    totals = await ledger.project_totals(
        organization_id=ORG, project_id=PROJECT, period=resolved.record.period
    )
    assert totals.unquantified_holds == 0


@pytest.mark.asyncio
async def test_resolving_a_marker_does_not_pretend_its_own_charge_was_applied() -> None:
    service, ledger, ownership, _, _ = accountant()
    call = call_context()
    await service.reserve(call=call, basis=price_basis(), operation_limit=None)
    ownership.failure = JobFenceLostError()
    first_proof = observation(call, charge="0.08")
    first = await service.record_observation(
        call=call, observation=first_proof, expected_call_revision=0
    )
    other_proof = observation(call, number=2, charge="0.15")
    second = await service.record_observation(
        call=call, observation=other_proof, expected_call_revision=first.record.revision
    )
    resolved_first = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=first_proof.evidence_id,
        authoritative_evidence_id=other_proof.evidence_id,
        expected_call_revision=second.record.revision,
    )
    later_marker = observation(call, number=3, kind="uncertain", charge=None)
    later = await service.record_observation(
        call=call, observation=later_marker, expected_call_revision=resolved_first.record.revision
    )
    corrected = await service.reconcile(
        access=ACCESS,
        project_id=PROJECT,
        call_id=call.call_id,
        pending_evidence_id=later_marker.evidence_id,
        authoritative_evidence_id=first_proof.evidence_id,
        expected_call_revision=later.record.revision,
    )
    assert corrected.record.settled_amount == money("0.08")
    assert (
        ledger.state.resolutions[(call.call_id, first_proof.evidence_id)].result
        == resolved_first.record
    )
    assert (
        ledger.state.evidence[(call.call_id, other_proof.evidence_id)][1] == resolved_first.record
    )
