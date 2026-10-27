from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID, uuid4

import pytest

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
    IdentityRecoveryCleanupClaimDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_run_dto import (
    IdentityRecoveryCleanupRunDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_step_dto import (
    IdentityRecoveryCleanupStepDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_event_dto import (
    IdentityRecoveryEventDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_step import (
    IdentityRecoveryCleanupStep,
)
from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.application.protocols.human_oauth_credential_revoker import (
    HumanOAuthCredentialRevoker,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_facts_reader import (
    IdentityRecoveryCleanupFactsReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_writer import (
    IdentityRecoveryCleanupWriter,
)
from inframeld_backend.access.application.services.identity_recovery_cleanup_execution_service import (
    IdentityRecoveryCleanupExecutionService,
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

CONFIRMED = HumanOAuthCleanupOutcomeDTO(
    State.CONFIRMED, OAuthCleanupDisposition.NOT_NEEDED, OAuthCleanupCategory.ACKNOWLEDGED, 204
)
RETRYABLE = HumanOAuthCleanupOutcomeDTO(
    State.UNCERTAIN, OAuthCleanupDisposition.RETRYABLE, OAuthCleanupCategory.PROVIDER_TIMEOUT
)
REJECTED = HumanOAuthCleanupOutcomeDTO(
    State.FAILED,
    OAuthCleanupDisposition.OPERATOR_REQUIRED,
    OAuthCleanupCategory.PROVIDER_REJECTION,
    403,
)


class Scenario(
    TransactionManager,
    IdentityRecoveryCleanupFactsReader,
    IdentityRecoveryCleanupWriter,
    HumanOAuthCredentialRevoker,
):
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.work: IdentityRecoveryCleanupWorkDTO | None = IdentityRecoveryCleanupWorkDTO(
            InstallationId(uuid4()),
            IdentityRecoveryAdmissionDTO(
                IdentityRecoveryEventDTO(
                    IdentityRecoveryFlowId(uuid4()),
                    VerifiedHumanIdentityDTO(
                        IdentityAuthority("kratos:test"), IdentitySubject("alice")
                    ),
                    IdentityRecoveryEventKind.RECOVERY,
                ),
                OperationId("original"),
            ),
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
                uuid4(), now, now + timedelta(hours=1), now, 12, 0, None, None
            ),
            None,
            (),
        )
        self.in_transaction = False
        self.calls: list[str] = []
        self.grant_outcome = CONFIRMED
        self.login_outcome = CONFIRMED
        self.proof_saved = False

    @override
    @asynccontextmanager
    async def begin(self) -> AsyncGenerator[None]:
        assert not self.in_transaction
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False

    @override
    async def next_candidate(self) -> OperationId | None:
        assert self.in_transaction
        return None if self.work is None else self.work.admission.operation_id

    @override
    async def lock_work(self, operation_id: OperationId) -> IdentityRecoveryCleanupWorkDTO | None:
        assert self.in_transaction
        return self.work

    @override
    async def claim(
        self,
        work: IdentityRecoveryCleanupWorkDTO,
        claim: IdentityRecoveryCleanupClaimDTO,
        *,
        at: datetime,
    ) -> None:
        assert self.in_transaction
        self.calls.append("claim")
        self.work = replace(
            work,
            claim=claim,
            steps=(),
            run=replace(work.run, consumed_attempts=work.run.consumed_attempts + 1),
        )

    @override
    async def admit_step(
        self,
        claim: IdentityRecoveryCleanupClaimDTO,
        step: IdentityRecoveryCleanupStep,
        *,
        at: datetime,
    ) -> None:
        assert self.in_transaction and self.work is not None
        self.calls.append("admit:" + step.value)
        self.work = replace(
            self.work, steps=(*self.work.steps, IdentityRecoveryCleanupStepDTO(step, at, None))
        )

    @override
    async def checkpoint(
        self,
        claim: IdentityRecoveryCleanupClaimDTO,
        step: IdentityRecoveryCleanupStep,
        outcome: HumanOAuthCleanupOutcomeDTO,
        *,
        at: datetime,
    ) -> None:
        assert self.in_transaction and self.work is not None
        self.calls.append("checkpoint:" + step.value)
        if step is IdentityRecoveryCleanupStep.CLI_GRANTS:
            self.work = replace(
                self.work,
                cli_grants_state=outcome.state,
                cli_confirmation_attempt_id=claim.attempt_id if outcome == CONFIRMED else None,
            )
        else:
            self.work = replace(
                self.work,
                remembered_logins_state=outcome.state,
                login_confirmation_attempt_id=claim.attempt_id if outcome == CONFIRMED else None,
            )
        self.work = replace(
            self.work,
            steps=tuple(
                replace(s, outcome=outcome) if s.step is step else s for s in self.work.steps
            ),
        )

    @override
    async def finish(
        self,
        work: IdentityRecoveryCleanupWorkDTO,
        *,
        at: datetime,
        terminal_reason: str | None,
        next_attempt_at: datetime | None = None,
    ) -> None:
        assert self.in_transaction
        self.calls.append("finish")
        self.work = replace(
            work,
            claim=None,
            run=replace(
                work.run,
                terminal_reason=terminal_reason,
                ended_at=at if terminal_reason else None,
                next_attempt_at=next_attempt_at or work.run.next_attempt_at,
            ),
        )

    @override
    async def save_complete_proof(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime
    ) -> None:
        assert self.in_transaction
        assert work.cli_grants_state is work.remembered_logins_state is State.CONFIRMED
        self.proof_saved = True

    @override
    async def revoke_cli_grants(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        assert not self.in_transaction and 0 < timeout_seconds <= 5
        assert subject == IdentitySubject("alice")
        self.calls.append("cli-grants")
        return self.grant_outcome

    @override
    async def revoke_remembered_logins(
        self, subject: IdentitySubject, *, timeout_seconds: float
    ) -> HumanOAuthCleanupOutcomeDTO:
        assert not self.in_transaction
        self.calls.append("remembered-logins")
        return self.login_outcome

    def service(self) -> IdentityRecoveryCleanupExecutionService:
        return IdentityRecoveryCleanupExecutionService(
            self, self, self, self, worker_id=UUID(int=42)
        )


@pytest.mark.asyncio
async def test_checkpoints_each_real_observation_before_next_dispatch() -> None:
    scenario = Scenario()
    assert await scenario.service().execute_once()
    assert scenario.calls == [
        "claim",
        "admit:cli-grants",
        "cli-grants",
        "checkpoint:cli-grants",
        "admit:remembered-logins",
        "remembered-logins",
        "checkpoint:remembered-logins",
        "finish",
    ]
    assert scenario.proof_saved and scenario.work is not None
    assert scenario.work.run.consumed_attempts == 1
    assert scenario.work.run.terminal_reason == "cleanup_confirmed"


@pytest.mark.asyncio
async def test_temporary_failure_retains_other_confirmation_and_schedules_once() -> None:
    scenario = Scenario()
    scenario.grant_outcome = RETRYABLE
    assert await scenario.service().execute_once()
    assert scenario.work is not None
    assert scenario.work.remembered_logins_state is State.CONFIRMED
    assert scenario.work.run.ended_at is None
    assert scenario.work.run.next_attempt_at > scenario.work.run.authorized_at
    assert not scenario.proof_saved


@pytest.mark.asyncio
async def test_known_permanent_rejection_stops_before_the_other_provider_call() -> None:
    scenario = Scenario()
    scenario.grant_outcome = REJECTED
    assert await scenario.service().execute_once()
    assert "remembered-logins" not in scenario.calls
    assert scenario.work is not None
    assert scenario.work.run.terminal_reason == "permanent_provider_rejection"


@pytest.mark.asyncio
async def test_missing_version_starts_no_attempt_or_provider_work() -> None:
    scenario = Scenario()
    assert scenario.work is not None
    scenario.work = replace(scenario.work, credential_version=None)
    assert await scenario.service().execute_once()
    assert scenario.calls == ["finish"]
    assert scenario.work is not None and scenario.work.run.consumed_attempts == 0
    assert scenario.work.run.next_attempt_at > scenario.work.run.authorized_at
    assert not scenario.proof_saved


@pytest.mark.asyncio
async def test_no_eligible_job_performs_no_work() -> None:
    scenario = Scenario()
    scenario.work = None
    assert not await scenario.service().execute_once()
    assert scenario.calls == []


@pytest.mark.asyncio
async def test_programming_failure_still_ends_the_run_without_an_automatic_retry() -> None:
    class BrokenRevoker(Scenario):
        @override
        async def revoke_cli_grants(
            self, subject: IdentitySubject, *, timeout_seconds: float
        ) -> HumanOAuthCleanupOutcomeDTO:
            raise RuntimeError("Unexpected programming failure.")

    scenario = BrokenRevoker()
    with pytest.raises(RuntimeError, match="Unexpected programming failure"):
        await scenario.service().execute_once()

    assert scenario.work is not None
    assert scenario.work.run.consumed_attempts == 1
    assert scenario.work.run.ended_at is not None
    assert scenario.work.run.terminal_reason == "unexpected_error"
    assert not scenario.proof_saved
    assert "remembered-logins" not in scenario.calls


@pytest.mark.asyncio
async def test_canceling_dispatched_work_preserves_the_consumed_claim_without_success() -> None:
    import asyncio

    class BlockedScenario(Scenario):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()

        @override
        async def revoke_cli_grants(
            self, subject: IdentitySubject, *, timeout_seconds: float
        ) -> HumanOAuthCleanupOutcomeDTO:
            assert not self.in_transaction
            self.started.set()
            await asyncio.Event().wait()
            return CONFIRMED

    scenario = BlockedScenario()
    task = asyncio.create_task(scenario.service().execute_once())
    try:
        async with asyncio.timeout(1):
            await scenario.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert scenario.work is not None and scenario.work.claim is not None
        assert scenario.work.run.consumed_attempts == 1
        assert scenario.work.cli_grants_state is State.PENDING
        assert not scenario.proof_saved and "finish" not in scenario.calls
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_a_replaced_worker_cannot_checkpoint_a_late_success() -> None:
    class ReplacedScenario(Scenario):
        @override
        async def revoke_cli_grants(
            self, subject: IdentitySubject, *, timeout_seconds: float
        ) -> HumanOAuthCleanupOutcomeDTO:
            assert self.work is not None and self.work.claim is not None
            self.work = replace(self.work, claim=replace(self.work.claim, token=uuid4()))
            return CONFIRMED

    scenario = ReplacedScenario()
    assert await scenario.service().execute_once()
    assert not scenario.proof_saved
    assert not any(event.startswith("checkpoint") for event in scenario.calls)
    assert scenario.work is not None and scenario.work.cli_grants_state is State.PENDING


@pytest.mark.asyncio
async def test_time_spent_committing_dispatch_cannot_extend_the_provider_budget() -> None:
    from unittest.mock import patch

    class Clock:
        current = datetime.now(UTC)

        @classmethod
        def now(cls, _timezone: object) -> datetime:
            return cls.current

    class DelayedCommitScenario(Scenario):
        @override
        @asynccontextmanager
        async def begin(self) -> AsyncGenerator[None]:
            async with super().begin():
                yield
            if "admit:cli-grants" in self.calls:
                assert self.work is not None
                Clock.current = self.work.run.deadline + timedelta(seconds=1)

    scenario = DelayedCommitScenario()
    Clock.current = datetime.now(UTC)
    with patch(
        "inframeld_backend.access.application.services.identity_recovery_cleanup_execution_service.datetime",
        Clock,
    ):
        assert await scenario.service().execute_once()
    assert "cli-grants" not in scenario.calls
    assert not scenario.proof_saved
