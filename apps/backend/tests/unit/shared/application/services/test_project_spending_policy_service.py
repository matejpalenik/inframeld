"""Exercise current human policy changes and replay without worker execution."""

from dataclasses import replace
from datetime import timedelta
from typing import override
from uuid import UUID

import pytest
from tests.unit.shared.application.services.test_spending_accounting_service import (
    ACCESS,
    NOW,
    ORG,
    PROJECT,
    MockBudgetAuthorizer,
    MockLedger,
    MockTransactions,
    accountant,
    call_context,
    money,
    price_basis,
)

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_authorization_dto import (
    ProjectActionAuthorizationDTO,
)
from inframeld_backend.access.application.protocols.authorized_operation_scope import (
    AuthorizedOperationScope,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.commands.change_project_spending_policy_command import (
    ChangeProjectSpendingPolicyCommand,
)
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.idempotency_context_dto import (
    IdempotencyContextDTO,
)
from inframeld_backend.shared.application.dtos.new_operation_reservation_dto import (
    NewOperationReservationDTO,
)
from inframeld_backend.shared.application.dtos.recovery_required_operation_dto import (
    RecoveryRequiredOperationDTO,
)
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.errors.application_errors import (
    AccessDeniedError,
    ConflictError,
    DependencyUnavailableError,
    StaleRevisionError,
)
from inframeld_backend.shared.application.errors.spending_errors import IncompleteSpendingFactsError
from inframeld_backend.shared.application.protocols.operation_idempotency import (
    OperationIdempotency,
)
from inframeld_backend.shared.application.services.project_spending_policy_fingerprint_service import (
    ProjectSpendingPolicyFingerprintService,
)
from inframeld_backend.shared.application.services.project_spending_policy_service import (
    ProjectSpendingPolicyService,
)
from inframeld_backend.shared.application.services.request_fingerprint_service import (
    RequestFingerprintService,
)
from inframeld_backend.shared.application.value_objects.idempotency_key import IdempotencyKey
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.operation_lookup_authority import (
    OperationLookupAuthority,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.application.value_objects.request_fingerprint_key import (
    RequestFingerprintKey,
)
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod

CONTEXT = IdempotencyContextDTO(
    "PATCH", "/projects/fixture/spending-policy", IdempotencyKey("policy-request")
)


class MockIdempotency(OperationIdempotency):
    def __init__(self, ledger: MockLedger) -> None:
        self.ledger = ledger
        self.fingerprint: RequestFingerprint | None = None
        self.completion: CompletedSynchronousOperationDTO | None = None
        self.failure: BaseException | None = None
        self.lookup_authorities: list[OperationLookupAuthority | None] = []

    @override
    async def reserve_or_recover[ProjectScope: ProjectId | None](
        self,
        *,
        context: IdempotencyContextDTO,
        access: AccessContextDTO,
        authorization: AuthorizedOperationScope[ProjectScope],
        fingerprint: RequestFingerprint,
        expected_replay_kind: OperationReplayKind,
        lookup_authority: OperationLookupAuthority | None = None,
    ) -> (
        NewOperationReservationDTO
        | CompletedSynchronousOperationDTO
        | AcceptedAsyncOperationDTO
        | RecoveryRequiredOperationDTO
    ):
        self.ledger.events.append("replay")
        self.lookup_authorities.append(lookup_authority)
        if self.fingerprint is not None and self.fingerprint != fingerprint:
            raise ConflictError("Retry key changed meaning.")
        self.fingerprint = fingerprint
        if self.completion is not None:
            return replace(self.completion, created=False)
        return NewOperationReservationDTO(OperationId("policy-original"))

    @override
    async def record_completed_result(
        self, operation: NewOperationReservationDTO, *, replay_kind: OperationReplayKind
    ) -> CompletedSynchronousOperationDTO | AcceptedAsyncOperationDTO:
        self.ledger.events.append("completion")
        if self.failure is not None:
            raise self.failure
        self.completion = CompletedSynchronousOperationDTO(
            operation.operation_id, True, OperationReplayKind.SAFE_RESULT, NOW + timedelta(days=1)
        )
        return self.completion


def manager(
    ledger: MockLedger | None = None,
) -> tuple[ProjectSpendingPolicyService, MockLedger, MockBudgetAuthorizer, MockIdempotency]:
    ledger = ledger if ledger is not None else MockLedger()
    authorizer = MockBudgetAuthorizer(ledger)
    idempotency = MockIdempotency(ledger)
    service = ProjectSpendingPolicyService(
        transaction_manager=MockTransactions(ledger),
        project_budget_authorizer=authorizer,
        spending_ledger_reader=ledger,
        spending_ledger_writer=ledger,
        operation_idempotency=idempotency,
        spending_policy_fingerprint_service=ProjectSpendingPolicyFingerprintService(
            RequestFingerprintService(RequestFingerprintKey(b"k" * 32))
        ),
    )
    return service, ledger, authorizer, idempotency


@pytest.mark.asyncio
async def test_current_human_management_precedes_replay_and_conditional_accounting_mutation() -> (
    None
):
    service, ledger, authorizer, _ = manager()
    result = await service.change_limit(
        access=ACCESS,
        command=ChangeProjectSpendingPolicyCommand(PROJECT, 0, money("2")),
        context=CONTEXT,
    )
    assert authorizer.actions == ["manage-budget"]
    assert result.policy.revision == 1
    assert result.policy.monthly_limit == money("2")
    assert result.changed and result.completion.created
    assert (
        ledger.events.index("budget-authorize")
        < ledger.events.index("replay")
        < ledger.events.index("ensure")
        < ledger.events.index("account")
    )
    assert ledger.state.audits == ["policy"]
    assert ledger.events[-1] == "commit"


@pytest.mark.asyncio
async def test_denied_or_wrong_scope_authority_never_reserves_or_initializes_accounting() -> None:
    service, ledger, authorizer, _ = manager()
    authorizer.failure = AccessDeniedError()
    with pytest.raises(AccessDeniedError):
        await service.change_limit(
            access=ACCESS,
            command=ChangeProjectSpendingPolicyCommand(PROJECT, 0, None),
            context=CONTEXT,
        )
    authorizer.failure = None
    authorizer.scope = ProjectActionAuthorizationDTO(ORG, ProjectId(UUID(int=99)))
    with pytest.raises(AccessDeniedError):
        await service.change_limit(
            access=ACCESS,
            command=ChangeProjectSpendingPolicyCommand(PROJECT, 0, None),
            context=CONTEXT,
        )
    assert "replay" not in ledger.events and "ensure" not in ledger.events


@pytest.mark.asyncio
async def test_stale_policy_revision_rolls_back_without_policy_audit() -> None:
    service, ledger, _, _ = manager()
    with pytest.raises(StaleRevisionError):
        await service.change_limit(
            access=ACCESS,
            command=ChangeProjectSpendingPolicyCommand(PROJECT, 8, None),
            context=CONTEXT,
        )
    assert ledger.state.policy.revision == 0 and not ledger.state.audits
    assert ledger.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_lost_response_replays_original_outcome_after_later_policy_change() -> None:
    service, ledger, authorizer, _ = manager()
    command = ChangeProjectSpendingPolicyCommand(PROJECT, 0, money("2"))
    original = await service.change_limit(access=ACCESS, command=command, context=CONTEXT)
    ledger.state.policy = replace(ledger.state.policy, revision=2, monthly_limit=money("3"))
    replay = await service.change_limit(access=ACCESS, command=command, context=CONTEXT)
    assert replay.policy == original.policy and not replay.completion.created
    assert ledger.state.policy.monthly_limit == money("3")
    assert ledger.state.audits == ["policy"]
    assert authorizer.actions == ["manage-budget", "manage-budget"]
    with pytest.raises(ConflictError):
        await service.change_limit(
            access=ACCESS, command=replace(command, monthly_limit=money("4")), context=CONTEXT
        )


@pytest.mark.asyncio
async def test_cap_install_preserves_unknown_original_obligation_and_denies_new_bounded_call() -> (
    None
):
    service, ledger, _, _ = manager()
    ledger.state.policy = replace(ledger.state.policy, monthly_limit=None)
    accounting, _, _, _, _ = accountant(ledger)
    original = await accounting.reserve(call=call_context(), basis=None, operation_limit=None)
    result = await service.change_limit(
        access=ACCESS,
        command=ChangeProjectSpendingPolicyCommand(PROJECT, 0, money("2")),
        context=CONTEXT,
    )
    assert result.policy.monthly_limit == money("2")
    assert ledger.state.calls[original.record.call_id] == original.record
    with pytest.raises(IncompleteSpendingFactsError):
        await accounting.reserve(call=call_context(2), basis=price_basis(), operation_limit=None)


@pytest.mark.asyncio
async def test_removing_cap_preserves_original_operation_limit_and_hold() -> None:
    service, ledger, _, _ = manager()
    accounting, _, _, _, _ = accountant(ledger)
    original = await accounting.reserve(
        call=call_context(), basis=price_basis(), operation_limit=money("1")
    )
    await service.change_limit(
        access=ACCESS, command=ChangeProjectSpendingPolicyCommand(PROJECT, 0, None), context=CONTEXT
    )
    assert ledger.state.calls[original.record.call_id] == original.record
    assert next(iter(ledger.state.operations.values()))[2] == money("1")


@pytest.mark.asyncio
async def test_identical_cap_is_a_retained_noop_without_revision_or_audit_change() -> None:
    service, ledger, _, _ = manager()
    result = await service.change_limit(
        access=ACCESS,
        command=ChangeProjectSpendingPolicyCommand(PROJECT, 0, money("1")),
        context=CONTEXT,
    )
    assert not result.changed and result.policy.revision == 0
    assert not ledger.state.audits and result.completion.created


@pytest.mark.asyncio
async def test_read_uses_one_projection_without_initializing_or_locking_accounting() -> None:
    service, ledger, authorizer, _ = manager()
    projection = await service.inspect(
        access=ACCESS, project_id=PROJECT, period=SpendingPeriod(2026, 11)
    )
    assert projection.remaining == money("1")
    assert authorizer.actions == ["inspect-budget"]
    assert ledger.events.count("projection") == 1
    assert "ensure" not in ledger.events and "account" not in ledger.events


@pytest.mark.asyncio
async def test_completion_failure_rolls_back_policy_and_audit() -> None:
    service, ledger, _, idempotency = manager()
    idempotency.failure = DependencyUnavailableError()
    with pytest.raises(DependencyUnavailableError):
        await service.change_limit(
            access=ACCESS,
            command=ChangeProjectSpendingPolicyCommand(PROJECT, 0, None),
            context=CONTEXT,
        )
    assert ledger.state.policy.monthly_limit == money("1")
    assert not ledger.state.audits and not ledger.state.results
    assert ledger.events[-1] == "rollback"


@pytest.mark.asyncio
async def test_review_policy_replay_retains_project_manage_budget_lookup_authority() -> None:
    service, _, _, idempotency = manager()
    await service.change_limit(
        access=ACCESS, command=ChangeProjectSpendingPolicyCommand(PROJECT, 0, None), context=CONTEXT
    )
    assert idempotency.lookup_authorities == [
        OperationLookupAuthority(
            OperationLookupAuthorityFamily.PROJECT_ACTION_USE, ActionId("manage-budget")
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("changed", ["organization", "project"])
@pytest.mark.parametrize("operation", ["lock", "projection", "replay"])
async def test_review_policy_records_cannot_cross_authorized_scope(
    changed: str, operation: str
) -> None:
    service, ledger, _, _ = manager()
    command = ChangeProjectSpendingPolicyCommand(PROJECT, 0, None)
    wrong = (
        replace(ledger.state.policy, organization_id=OrganizationId(UUID(int=99)))
        if changed == "organization"
        else replace(ledger.state.policy, project_id=ProjectId(UUID(int=99)))
    )
    if operation == "lock":
        ledger.returned_policy = wrong
    elif operation == "projection":
        projection = await ledger.project_projection(
            organization_id=ORG, project_id=PROJECT, period=SpendingPeriod(2026, 11)
        )
        ledger.returned_projection = replace(projection, policy=wrong)
    else:
        original = await service.change_limit(access=ACCESS, command=command, context=CONTEXT)
        ledger.returned_policy_result = replace(original, policy=wrong)
    previous = ledger.state.policy
    with pytest.raises(RuntimeError):
        if operation == "projection":
            await service.inspect(
                access=ACCESS, project_id=PROJECT, period=SpendingPeriod(2026, 11)
            )
        else:
            await service.change_limit(access=ACCESS, command=command, context=CONTEXT)
    assert ledger.state.policy == previous
