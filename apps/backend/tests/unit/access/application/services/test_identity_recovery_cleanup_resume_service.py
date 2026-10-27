import asyncio
from collections import deque
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import uuid4

import pytest

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
    IdentityRecoveryCleanupClaimDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_facts_dto import (
    IdentityRecoveryCleanupResumeFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_run_dto import (
    IdentityRecoveryCleanupRunDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_completion_facts_dto import (
    IdentityRecoveryCompletionFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_maintenance_receipt_dto import (
    IdentityRecoveryMaintenanceReceiptDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_resume_outcome import (
    IdentityRecoveryCleanupResumeOutcome as Outcome,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.recovery_maintenance_error_code import (
    RecoveryMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.recovery_maintenance_error import (
    RecoveryMaintenanceError,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_resume_facts_reader import (
    IdentityRecoveryCleanupResumeFactsReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_resume_writer import (
    IdentityRecoveryCleanupResumeWriter,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_facts_reader import (
    IdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_resume_service import (
    IdentityRecoveryCleanupResumeService,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId

pytestmark = pytest.mark.asyncio


class _FakeTransactions(TransactionManager):
    def __init__(self, trace: list[str]) -> None:
        self._trace = trace
        self.active = False
        self.committed = False
        self.rolled_back = False

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        assert not self.active
        self.active = True
        self.committed = self.rolled_back = False
        self._trace.append("transaction.begin")
        try:
            yield
        except BaseException:
            self.rolled_back = True
            self._trace.append("transaction.rollback")
            raise
        else:
            self.committed = True
            self._trace.append("transaction.commit")
        finally:
            self.active = False


class _FakeResumeFactsReader(IdentityRecoveryCleanupResumeFactsReader):
    def __init__(
        self,
        transactions: _FakeTransactions,
        trace: list[str],
        work: IdentityRecoveryCleanupWorkDTO,
    ) -> None:
        self._transactions = transactions
        self._trace = trace
        self.installed: InstallationId | None = work.installation_id
        self.recorded_receipt: IdentityRecoveryMaintenanceReceiptDTO | None = None
        self.receipt_results: deque[IdentityRecoveryMaintenanceReceiptDTO | None] = deque()
        self.admission: IdentityRecoveryAdmissionDTO | None = work.admission
        self.observations = IdentityRecoveryCleanupResumeFactsDTO(
            None, State.CONFIRMED, State.PENDING, False, work
        )
        self.receipt_calls: list[tuple[InstallationId, OperationId]] = []
        self.original_calls: list[tuple[InstallationId, OperationId]] = []
        self.read_calls: list[tuple[InstallationId, IdentityRecoveryAdmissionDTO]] = []

    @override
    async def installation(self) -> InstallationId | None:
        assert self._transactions.active
        self._trace.append("facts.installation")
        return self.installed

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> IdentityRecoveryMaintenanceReceiptDTO | None:
        assert self._transactions.active
        self.receipt_calls.append((installation_id, operation_id))
        self._trace.append("facts.receipt")
        if self.receipt_results:
            return self.receipt_results.popleft()
        return self.recorded_receipt

    @override
    async def original(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> IdentityRecoveryAdmissionDTO | None:
        assert self._transactions.active
        self.original_calls.append((installation_id, operation_id))
        self._trace.append("facts.original")
        return self.admission

    @override
    async def read(
        self, *, installation_id: InstallationId, admission: IdentityRecoveryAdmissionDTO
    ) -> IdentityRecoveryCleanupResumeFactsDTO:
        assert self._transactions.active
        self.read_calls.append((installation_id, admission))
        self._trace.append("facts.read")
        return self.observations


class _FakeCompletionFactsReader(IdentityRecoveryCompletionFactsReader):
    def __init__(
        self,
        transactions: _FakeTransactions,
        trace: list[str],
        work: IdentityRecoveryCleanupWorkDTO,
    ) -> None:
        self._transactions = transactions
        self._trace = trace
        self.result = IdentityRecoveryCompletionFactsDTO(
            work.installation_id, work.admission, None, False, HumanCredentialVersion(2)
        )
        self.read_calls: list[tuple[InstallationId, IdentityAuthority, IdentityRecoveryFlowId]] = []
        self.entered = asyncio.Event()
        self.allowed = asyncio.Event()
        self.allowed.set()

    @override
    async def read(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecoveryCompletionFactsDTO:
        assert self._transactions.active
        self.read_calls.append((installation_id, authority, flow_id))
        self._trace.append("coordination.read")
        self.entered.set()
        await self.allowed.wait()
        return self.result


class _FakeResumeWriter(IdentityRecoveryCleanupResumeWriter):
    def __init__(self, transactions: _FakeTransactions, trace: list[str]) -> None:
        self._transactions = transactions
        self._trace = trace
        self.record_wins = True
        self.record_calls: list[IdentityRecoveryMaintenanceReceiptDTO] = []
        self.authorizations: list[IdentityRecoveryMaintenanceReceiptDTO] = []
        self.settlements: list[tuple[IdentityRecoveryCleanupWorkDTO, datetime, str]] = []
        self.proofs: list[tuple[IdentityRecoveryCleanupWorkDTO, datetime]] = []

    @override
    async def record(self, receipt: IdentityRecoveryMaintenanceReceiptDTO) -> bool:
        assert self._transactions.active
        self.record_calls.append(receipt)
        self._trace.append("writer.record")
        return self.record_wins

    @override
    async def authorize_run(self, receipt: IdentityRecoveryMaintenanceReceiptDTO) -> None:
        assert self._transactions.active
        self.authorizations.append(receipt)
        self._trace.append("writer.authorize")

    @override
    async def settle(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime, terminal_reason: str
    ) -> None:
        assert self._transactions.active
        self.settlements.append((work, at, terminal_reason))
        self._trace.append("writer.settle")

    @override
    async def save_complete_proof(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime
    ) -> None:
        assert self._transactions.active
        self.proofs.append((work, at))
        self._trace.append("writer.proof")


@dataclass
class Scenario:
    command: ResumeIdentityRecoveryCleanupCommand
    work: IdentityRecoveryCleanupWorkDTO
    facts: _FakeResumeFactsReader
    coordination: _FakeCompletionFactsReader
    writer: _FakeResumeWriter
    transactions: _FakeTransactions
    trace: list[str]

    def service(self) -> IdentityRecoveryCleanupResumeService:
        return IdentityRecoveryCleanupResumeService(
            self.transactions, self.facts, self.coordination, self.writer
        )


def _scenario() -> Scenario:
    now = datetime.now(UTC)
    installation = InstallationId(uuid4())
    command = ResumeIdentityRecoveryCleanupCommand(
        installation,
        OperationId("host-request"),
        OperationId("original"),
        "Operator",
        "Hydra repaired",
    )
    admission = IdentityRecoveryAdmissionDTO(
        IdentityRecoveryEventDTO(
            IdentityRecoveryFlowId(uuid4()),
            VerifiedHumanIdentityDTO(IdentityAuthority("kratos:test"), IdentitySubject("Alice")),
            IdentityRecoveryEventKind.RECOVERY,
        ),
        command.recovery_operation_id,
    )
    work = IdentityRecoveryCleanupWorkDTO(
        installation,
        admission,
        uuid4(),
        True,
        HumanCredentialVersion(2),
        State.CONFIRMED,
        None,
        State.PENDING,
        State.PENDING,
        None,
        None,
        IdentityRecoveryCleanupRunDTO(
            uuid4(), now, now + timedelta(hours=1), now, 12, 1, now, "permanent_provider_rejection"
        ),
        None,
        (),
    )
    trace: list[str] = []
    transactions = _FakeTransactions(trace)
    facts = _FakeResumeFactsReader(transactions, trace, work)
    coordination = _FakeCompletionFactsReader(transactions, trace, work)
    writer = _FakeResumeWriter(transactions, trace)
    return Scenario(command, work, facts, coordination, writer, transactions, trace)


async def test_authorization_records_receipt_before_run_and_preserves_original() -> None:
    s = _scenario()
    result = await s.service().resume(command=s.command)
    assert result.outcome is Outcome.AUTHORIZED
    receipt = s.writer.record_calls[0]
    assert receipt.command == s.command
    assert result.deadline == receipt.authorized_at + timedelta(hours=1)
    assert result.run_id != s.work.run.id
    assert s.writer.authorizations == [receipt]
    assert not s.writer.settlements
    assert [call for call in s.trace if call.startswith("writer.")] == [
        "writer.record",
        "writer.authorize",
    ]
    assert s.facts.original_calls == [
        (s.command.expected_installation_id, s.command.recovery_operation_id)
    ]
    assert s.coordination.read_calls == [
        (
            s.work.installation_id,
            s.work.admission.event.identity.authority,
            s.work.admission.event.flow_id,
        )
    ]
    assert s.facts.read_calls == [(s.work.installation_id, s.work.admission)]
    assert s.transactions.committed and not s.transactions.rolled_back


async def test_replay_precedes_target_and_active_run_checks() -> None:
    s = _scenario()
    original = IdentityRecoveryCleanupResumeResultDTO(
        s.command.operation_id,
        s.command.expected_installation_id,
        s.command.recovery_operation_id,
        Outcome.ALREADY_COMPLETED,
        True,
    )
    s.facts.recorded_receipt = IdentityRecoveryMaintenanceReceiptDTO(
        s.command, datetime.now(UTC), original
    )
    assert await s.service().resume(command=s.command) == original
    assert not s.facts.original_calls
    assert not s.coordination.read_calls
    assert not s.writer.record_calls


async def test_installation_is_verified_before_replay() -> None:
    s = _scenario()
    s.facts.installed = InstallationId(uuid4())
    with pytest.raises(RecoveryMaintenanceError) as error:
        await s.service().resume(command=s.command)
    assert error.value.code is Code.INSTALLATION_MISMATCH
    assert not s.facts.receipt_calls


@pytest.mark.parametrize("field", ["reason", "operator_label", "recovery_operation_id"])
async def test_changed_meaning_conflicts(field: str) -> None:
    s = _scenario()
    changed = replace(
        s.command, **{field: OperationId("other") if field == "recovery_operation_id" else "other"}
    )
    result = IdentityRecoveryCleanupResumeResultDTO(
        s.command.operation_id,
        s.command.expected_installation_id,
        s.command.recovery_operation_id,
        Outcome.ALREADY_COMPLETED,
        True,
    )
    s.facts.recorded_receipt = IdentityRecoveryMaintenanceReceiptDTO(
        changed, datetime.now(UTC), result
    )
    with pytest.raises(RecoveryMaintenanceError) as error:
        await s.service().resume(command=s.command)
    assert error.value.code is Code.KEY_REUSED


@pytest.mark.parametrize("consumed,lease_seconds", [(1, -1), (12, 30)])
async def test_expired_lease_or_live_final_attempt_does_not_grant_budget(
    consumed: int, lease_seconds: int
) -> None:
    s = _scenario()
    claim = IdentityRecoveryCleanupClaimDTO(
        s.command.recovery_operation_id,
        s.work.run.id,
        uuid4(),
        uuid4(),
        uuid4(),
        datetime.now(UTC) + timedelta(seconds=lease_seconds),
    )
    work = replace(
        s.work,
        run=replace(s.work.run, ended_at=None, terminal_reason=None, consumed_attempts=consumed),
        claim=claim,
    )
    s.facts.observations = replace(s.facts.observations, work=work)
    with pytest.raises(RecoveryMaintenanceError) as error:
        await s.service().resume(command=s.command)
    assert error.value.code is Code.RUN_ACTIVE
    assert not s.writer.record_calls


async def test_expired_final_attempt_is_settled_after_receipt_before_replacement() -> None:
    s = _scenario()
    claim = IdentityRecoveryCleanupClaimDTO(
        s.command.recovery_operation_id,
        s.work.run.id,
        uuid4(),
        uuid4(),
        uuid4(),
        datetime.now(UTC) - timedelta(seconds=1),
    )
    work = replace(
        s.work, run=replace(s.work.run, ended_at=None, consumed_attempts=12), claim=claim
    )
    s.facts.observations = replace(s.facts.observations, work=work)
    await s.service().resume(command=s.command)
    assert len(s.writer.settlements) == 1
    assert s.writer.settlements[0][2] == "attempt_budget_exhausted"
    assert [call for call in s.trace if call.startswith("writer.")] == [
        "writer.record",
        "writer.settle",
        "writer.authorize",
    ]


@pytest.mark.parametrize("released,covered", [(True, False), (False, True)])
async def test_no_run_receipts_cover_released_and_newer_proof_without_job(
    released: bool, covered: bool
) -> None:
    s = _scenario()
    s.facts.observations = IdentityRecoveryCleanupResumeFactsDTO(
        datetime.now(UTC) if released else None, State.CONFIRMED, State.CONFIRMED, covered, None
    )
    result = await s.service().resume(command=s.command)
    assert result.outcome is (Outcome.ALREADY_COMPLETED if released else Outcome.CLEANUP_CONFIRMED)
    assert result.run_id is None
    assert len(s.writer.record_calls) == 1
    assert not s.writer.authorizations


@pytest.mark.parametrize("missing", ["evidence", "version", "job"])
async def test_missing_prerequisites_never_persist_authorization(missing: str) -> None:
    s = _scenario()
    if missing == "version":
        s.coordination.result = replace(s.coordination.result, credential_version=None)
    elif missing == "evidence":
        s.facts.observations = replace(s.facts.observations, kratos_cleanup_state=State.PENDING)
    else:
        s.facts.observations = replace(s.facts.observations, work=None)
    with pytest.raises(RecoveryMaintenanceError) as error:
        await s.service().resume(command=s.command)
    assert error.value.code is (
        Code.DEPENDENCY_UNAVAILABLE if missing == "version" else Code.EVIDENCE_MISSING
    )
    assert not s.writer.record_calls


async def test_receipt_race_loser_replays_winner_without_effects() -> None:
    s = _scenario()
    winner = IdentityRecoveryCleanupResumeResultDTO(
        s.command.operation_id,
        s.command.expected_installation_id,
        s.command.recovery_operation_id,
        Outcome.ALREADY_COMPLETED,
        True,
    )
    s.writer.record_wins = False
    s.facts.receipt_results = deque(
        [
            None,
            None,
            IdentityRecoveryMaintenanceReceiptDTO(s.command, datetime.now(UTC), winner),
        ]
    )
    assert await s.service().resume(command=s.command) == winner
    assert not s.writer.settlements
    assert not s.writer.authorizations


async def test_cancellation_propagates_before_persistence() -> None:
    s = _scenario()
    s.coordination.allowed.clear()
    task = asyncio.create_task(s.service().resume(command=s.command))
    try:
        async with asyncio.timeout(5):
            await s.coordination.entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert not s.writer.record_calls
        assert s.transactions.rolled_back and not s.transactions.committed
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def test_missing_direct_proof_is_saved_without_another_run() -> None:
    s = _scenario()
    work = replace(
        s.work,
        cli_grants_state=State.CONFIRMED,
        remembered_logins_state=State.CONFIRMED,
        cli_confirmation_attempt_id=uuid4(),
        login_confirmation_attempt_id=uuid4(),
    )
    s.facts.observations = replace(s.facts.observations, work=work)
    result = await s.service().resume(command=s.command)
    assert result.outcome is Outcome.CLEANUP_CONFIRMED
    assert len(s.writer.proofs) == 1
    assert not s.writer.authorizations


async def test_existing_checked_proof_is_not_requeued_for_eligibility() -> None:
    s = _scenario()
    s.facts.observations = replace(s.facts.observations, has_complete_proof=True)
    result = await s.service().resume(command=s.command)
    assert result.outcome is Outcome.CLEANUP_CONFIRMED
    assert not s.writer.proofs
    assert not s.writer.settlements
    assert not s.writer.authorizations


async def test_existing_local_confirmation_without_job_does_not_invent_proof_or_restart_cleanup() -> (
    None
):
    s = _scenario()
    s.facts.observations = IdentityRecoveryCleanupResumeFactsDTO(
        None, State.CONFIRMED, State.CONFIRMED, False, None
    )
    result = await s.service().resume(command=s.command)
    assert result.outcome is Outcome.CLEANUP_CONFIRMED
    assert not s.writer.proofs
    assert not s.writer.authorizations
