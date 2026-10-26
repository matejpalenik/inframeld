import asyncio
import random
from collections.abc import AsyncGenerator, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import override
from uuid import UUID, uuid4

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
    IdentityRecoveryCleanupClaimDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_step import (
    IdentityRecoveryCleanupStep,
)
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.application.protocols.human_oauth_credential_revoker import (
    HumanOAuthCredentialRevoker,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_executor import (
    IdentityRecoveryCleanupExecutor,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_facts_reader import (
    IdentityRecoveryCleanupFactsReader,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_writer import (
    IdentityRecoveryCleanupWriter,
)
from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class IdentityRecoveryCleanupExecutionService(IdentityRecoveryCleanupExecutor):
    """Consume one original run attempt and checkpoint its two fixed provider steps.

    Bootstrap supplies clean session-bound capabilities. No transaction or
    coordination lock remains open during a provider call.
    """

    def __init__(
        self,
        transactions: TransactionManager,
        facts: IdentityRecoveryCleanupFactsReader,
        writer: IdentityRecoveryCleanupWriter,
        revoker: HumanOAuthCredentialRevoker,
        *,
        worker_id: UUID,
        provider_timeout_seconds: float = 5,
        database_timeout_seconds: float = 5,
        lease_seconds: float = 60,
        stop_requested: Callable[[], bool] = lambda: False,
    ) -> None:
        self._transactions = transactions
        self._facts = facts
        self._writer = writer
        self._revoker = revoker
        self._worker_id = worker_id
        self._provider_timeout_seconds = provider_timeout_seconds
        self._database_timeout_seconds = database_timeout_seconds
        self._lease_seconds = lease_seconds
        self._stop_requested = stop_requested

    @asynccontextmanager
    async def _stage(self) -> AsyncGenerator[None]:
        try:
            async with asyncio.timeout(self._database_timeout_seconds):
                async with self._transactions.begin():
                    yield
        except TimeoutError:
            raise DependencyUnavailableError(
                "Recovery database work exceeded its deadline."
            ) from None

    @override
    async def execute_once(self) -> bool:
        if self._stop_requested():
            return False

        async with self._stage():
            operation_id = await self._facts.next_candidate()
            if operation_id is None:
                return False

            work = await self._facts.lock_work(operation_id)
            if work is None:
                return False

            if work.admission.operation_id != operation_id:
                raise RuntimeError("Cleanup facts do not match the original operation.")

            now = datetime.now(UTC)
            if work.credential_version is None:
                # Retain the block and let other identities proceed without an attempt.
                next_at = now + timedelta(seconds=15)
                await self._writer.finish(
                    work,
                    at=now,
                    terminal_reason="deadline_exhausted" if next_at >= work.run.deadline else None,
                    next_attempt_at=next_at if next_at < work.run.deadline else None,
                )
                return True

            self._require_proof_inputs(work)
            if work.run.ended_at is not None:
                return False

            if work.claim is not None:
                if work.claim.lease_expires_at > now:
                    return False
                await self._finish(work, now)
                return True

            if work.released_at is not None:
                await self._writer.finish(
                    work,
                    at=now,
                    terminal_reason="cleanup_confirmed"
                    if self._confirmed(work)
                    else "unexpected_error",
                )
                return True

            if self._confirmed(work):
                await self._finish(work, now)
                return True

            if now >= work.run.deadline or work.run.consumed_attempts >= work.run.max_attempts:
                await self._writer.finish(
                    work,
                    at=now,
                    terminal_reason="deadline_exhausted"
                    if now >= work.run.deadline
                    else "attempt_budget_exhausted",
                )
                return True

            if work.run.next_attempt_at > now:
                return False

            claim = IdentityRecoveryCleanupClaimDTO(
                operation_id,
                work.run.id,
                uuid4(),
                self._worker_id,
                uuid4(),
                now + timedelta(seconds=self._lease_seconds),
            )
            await self._writer.claim(work, claim, at=now)

        try:
            for step in IdentityRecoveryCleanupStep:
                async with self._stage():
                    current = await self._owned_work(claim)
                    if current is None:
                        return True

                    now = datetime.now(UTC)
                    if self._stop_requested() or now >= current.run.deadline:
                        break

                    state = (
                        current.cli_grants_state
                        if step is IdentityRecoveryCleanupStep.CLI_GRANTS
                        else current.remembered_logins_state
                    )
                    if state is IdentityRecoveryCleanupState.CONFIRMED:
                        continue

                    timeout = min(
                        self._provider_timeout_seconds,
                        (current.run.deadline - now).total_seconds(),
                        (claim.lease_expires_at - now).total_seconds(),
                    )
                    if timeout <= 0:
                        break
                    await self._writer.admit_step(claim, step, at=now)

                now = datetime.now(UTC)
                timeout = min(
                    timeout,
                    (current.run.deadline - now).total_seconds(),
                    (claim.lease_expires_at - now).total_seconds(),
                )
                if timeout <= 0 or self._stop_requested():
                    break

                # Admission is committed. A later stop cannot recall this remote call.
                outcome = await (
                    self._revoker.revoke_cli_grants(
                        work.admission.event.identity.subject, timeout_seconds=timeout
                    )
                    if step is IdentityRecoveryCleanupStep.CLI_GRANTS
                    else self._revoker.revoke_remembered_logins(
                        work.admission.event.identity.subject, timeout_seconds=timeout
                    )
                )

                async with self._stage():
                    if await self._owned_work(claim) is None:
                        return True
                    await self._writer.checkpoint(claim, step, outcome, at=datetime.now(UTC))

                if outcome.disposition is OAuthCleanupDisposition.OPERATOR_REQUIRED:
                    break

            async with self._stage():
                current = await self._owned_work(claim)
                if current is not None:
                    await self._finish(current, datetime.now(UTC))
        except (asyncio.CancelledError, DependencyUnavailableError):
            # A replacement consumes the saved attempt after lease expiry.
            raise
        except Exception:
            # Do not turn a programming failure into a retryable provider result.
            async with self._stage():
                current = await self._owned_work(claim)
                if current is not None:
                    await self._writer.finish(
                        current, at=datetime.now(UTC), terminal_reason="unexpected_error"
                    )
            raise

        return True

    async def _owned_work(
        self, claim: IdentityRecoveryCleanupClaimDTO
    ) -> IdentityRecoveryCleanupWorkDTO | None:
        current = await self._facts.lock_work(claim.operation_id)
        if (
            current is None
            or current.claim != claim
            or current.run.ended_at is not None
            or claim.lease_expires_at <= datetime.now(UTC)
        ):
            return None

        self._require_proof_inputs(current)
        return current

    @staticmethod
    def _confirmed(work: IdentityRecoveryCleanupWorkDTO) -> bool:
        return (
            work.cli_grants_state
            is work.remembered_logins_state
            is IdentityRecoveryCleanupState.CONFIRMED
        )

    @staticmethod
    def _require_proof_inputs(work: IdentityRecoveryCleanupWorkDTO) -> None:
        if (
            not work.has_original_password_receipt
            or work.kratos_cleanup_state is not IdentityRecoveryCleanupState.CONFIRMED
        ):
            raise RuntimeError("Cleanup requires its original trusted Kratos evidence.")

        if work.credential_version is None:
            raise DependencyUnavailableError("Recovery credential state is unavailable.")

        budget = IdentityRecoveryCleanupRunBudget(work.run.authorized_at)
        if work.run.deadline != budget.deadline or work.run.max_attempts != budget.max_attempts:
            raise RuntimeError("The stored cleanup budget is inconsistent.")

    async def _finish(self, work: IdentityRecoveryCleanupWorkDTO, now: datetime) -> None:
        if self._confirmed(work):
            await self._writer.save_complete_proof(work, at=now)
            await self._writer.finish(work, at=now, terminal_reason="cleanup_confirmed")
            return

        outcomes = [step.outcome for step in work.steps if step.outcome is not None]
        permanent = next(
            (o for o in outcomes if o.disposition is OAuthCleanupDisposition.OPERATOR_REQUIRED),
            None,
        )
        if permanent is not None:
            reason = (
                "permanent_provider_rejection"
                if permanent.state is IdentityRecoveryCleanupState.FAILED
                else "provider_protocol_error"
            )
            await self._writer.finish(work, at=now, terminal_reason=reason)
            return

        budget = IdentityRecoveryCleanupRunBudget(work.run.authorized_at)
        if work.run.consumed_attempts >= budget.max_attempts or now >= budget.deadline:
            await self._writer.finish(
                work,
                at=now,
                terminal_reason="attempt_budget_exhausted"
                if work.run.consumed_attempts >= budget.max_attempts
                else "deadline_exhausted",
            )
            return

        delay = max((outcome.retry_after_seconds or 0 for outcome in outcomes), default=0)
        next_at = budget.retry_at(
            attempt_number=work.run.consumed_attempts,
            failed_at=now,
            jitter_seconds=random.randint(1, min(600, 15 * 2 ** (work.run.consumed_attempts - 1))),
            retry_after_seconds=delay,
        )
        await self._writer.finish(
            work,
            at=now,
            terminal_reason="deadline_exhausted" if next_at is None else None,
            next_attempt_at=next_at,
        )
