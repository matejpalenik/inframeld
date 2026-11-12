from typing import override
from uuid import UUID

from sqlalchemy import DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.human_suspension_cleanup_dispatch_dto import (
    HumanSuspensionCleanupDispatchDTO,
)
from inframeld_backend.access.application.protocols.human_suspension_cleanup_checkpoint_writer import (
    HumanSuspensionCleanupCheckpointWriter,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.shared.application.dtos.human_suspension_job_facts_dto import (
    HumanSuspensionJobFactsDTO,
)
from inframeld_backend.shared.application.dtos.job_attempt_context_dto import JobAttemptContextDTO
from inframeld_backend.shared.application.enums.human_suspension_cleanup_step import (
    HumanSuspensionCleanupStep,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.services.human_suspension_job_authorization_service import (
    HumanSuspensionJobAuthorizationService,
)
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.readers.postgres_human_suspension_job_facts_reader import (
    PostgresHumanSuspensionJobFactsReader,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_attempt_row import (
    DurableJobAttemptRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.human_suspension_obligation_row import (
    HumanSuspensionObligationRow,
)


class PostgresHumanSuspensionCleanupCheckpointWriter(HumanSuspensionCleanupCheckpointWriter):
    """Save one suspension cleanup step inside the caller's short transaction.

    The caller commits begin before external work and confirms in a later transaction.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._facts = PostgresHumanSuspensionJobFactsReader(session)
        self._authorizer = HumanSuspensionJobAuthorizationService(self._facts)

    async def begin(
        self, context: JobAttemptContextDTO, *, worker_id: UUID, step: HumanSuspensionCleanupStep
    ) -> None:
        """Flush a pending marker. Any later dispatch needs a known commit."""
        await self._mark(context, worker_id=worker_id, step=step, skip_confirmed=False)

    @override
    async def prepare_dispatch(
        self, context: JobAttemptContextDTO, *, worker_id: UUID, step: HumanSuspensionCleanupStep
    ) -> HumanSuspensionCleanupDispatchDTO | None:
        facts = await self._mark(context, worker_id=worker_id, step=step, skip_confirmed=True)
        if facts is None:
            return None
        return HumanSuspensionCleanupDispatchDTO(
            facts.binding.identity,
            (min(facts.lease_expires_at, facts.work_deadline) - facts.observed_at).total_seconds(),
        )

    async def _mark(
        self,
        context: JobAttemptContextDTO,
        *,
        worker_id: UUID,
        step: HumanSuspensionCleanupStep,
        skip_confirmed: bool,
    ) -> HumanSuspensionJobFactsDTO | None:
        child, parent, marker, facts = await self._pending(
            context, worker_id=worker_id, step=step, require_pending=False
        )
        state = self._facts.step_states(parent)[step]
        if skip_confirmed and state is IdentityRecoveryCleanupState.CONFIRMED:
            return None
        if child.pending_effect is not None:
            repeat = await self._facts.lock_unused_repeat(parent, child)
            if repeat is None or repeat[1] is not step or repeat[2].number >= facts.attempt:
                raise ConflictError("An original suspension cleanup marker is unresolved.")
            receipt, _, earlier = repeat
            now = await self._session.scalar(
                select(func.clock_timestamp(type_=DateTime(timezone=True)))
            )
            if now is None:
                raise DependencyUnavailableError("The authoritative database clock is unavailable.")
            if not receipt.authorized_at <= now < min(facts.lease_expires_at, facts.work_deadline):
                raise ConflictError("The authorized suspension repeat is no longer live.")
            outcome = state
            if outcome is IdentityRecoveryCleanupState.PENDING:
                outcome = IdentityRecoveryCleanupState.UNCERTAIN
            earlier.reason = f"suspension_repeat:{step.value}:{outcome.value}"
            receipt.suspension_repeat_consumed_at = now
            self._set_step_state(parent, step, IdentityRecoveryCleanupState.PENDING)
        elif state is not IdentityRecoveryCleanupState.PENDING:
            raise ConflictError("The original suspension cleanup step must still be pending.")

        child.pending_effect = marker
        await self._session.flush()
        return facts

    @override
    async def confirm(
        self, context: JobAttemptContextDTO, *, worker_id: UUID, step: HumanSuspensionCleanupStep
    ) -> None:
        """Confirm the marked step and retire the live attempt when all steps are complete."""
        child, parent, marker, facts = await self._pending(context, worker_id=worker_id, step=step)
        if child.pending_effect != marker:
            raise ConflictError("Confirmation must match the original suspension cleanup marker.")

        if all(
            state is IdentityRecoveryCleanupState.CONFIRMED
            for other_step, state in self._facts.step_states(parent).items()
            if other_step is not step
        ):
            parent.completed_at = facts.observed_at
            await self._close_attempt(child, facts, status=JobStatus.SUCCEEDED, reason=None)

        self._set_step_state(parent, step, IdentityRecoveryCleanupState.CONFIRMED)
        child.pending_effect = None
        await self._session.flush()

    async def record_nonconfirmation(
        self,
        context: JobAttemptContextDTO,
        *,
        worker_id: UUID,
        step: HumanSuspensionCleanupStep,
        outcome: IdentityRecoveryCleanupState,
    ) -> None:
        """Retain the observed outcome and marker for the exact live step."""
        await self._save_nonconfirmation(
            context, worker_id=worker_id, step=step, outcome=outcome, stop=False
        )

    @override
    async def stop_unconfirmed(
        self,
        context: JobAttemptContextDTO,
        *,
        worker_id: UUID,
        step: HumanSuspensionCleanupStep,
        outcome: IdentityRecoveryCleanupState,
    ) -> None:
        """End the exact attempt and retain its unresolved marker and observation."""
        await self._save_nonconfirmation(
            context, worker_id=worker_id, step=step, outcome=outcome, stop=True
        )

    async def _save_nonconfirmation(
        self,
        context: JobAttemptContextDTO,
        *,
        worker_id: UUID,
        step: HumanSuspensionCleanupStep,
        outcome: IdentityRecoveryCleanupState,
        stop: bool,
    ) -> None:
        if (
            outcome is not IdentityRecoveryCleanupState.FAILED
            and outcome is not IdentityRecoveryCleanupState.UNCERTAIN
        ):
            raise ValueError("Nonconfirmation requires a failed or uncertain outcome.")

        child, parent, marker, facts = await self._pending(context, worker_id=worker_id, step=step)
        if child.pending_effect != marker:
            raise ConflictError(
                "Nonconfirmation must match the original suspension cleanup marker."
            )

        self._set_step_state(parent, step, outcome)
        if stop:
            if facts.observed_at >= parent.queued_deadline:
                parent.queue_exhausted_at = facts.observed_at
            await self._close_attempt(
                child,
                facts,
                status=JobStatus.RECOVERY_REQUIRED,
                reason="provider_outcome_uncertain",
            )
        await self._session.flush()

    async def _close_attempt(
        self,
        child: DurableJobRow,
        facts: HumanSuspensionJobFactsDTO,
        *,
        status: JobStatus,
        reason: str | None,
    ) -> None:
        # The current authorization holds the child and attempt locks until caller commit.
        with self._session.no_autoflush:
            attempt = await self._session.get(DurableJobAttemptRow, (child.id, facts.attempt))
        if (
            attempt is None
            or attempt.ended_at is not None
            or attempt.fence != facts.fence.value
            or attempt.worker_id != facts.worker_id
        ):
            raise ConflictError("The original suspension cleanup attempt is no longer open.")

        child.status = status.value
        child.terminal_at = facts.observed_at
        child.fence = None
        child.worker_id = None
        child.lease_expires_at = None
        child.reason = reason
        attempt.ended_at = facts.observed_at
        attempt.reason = reason

    async def _pending(
        self,
        context: JobAttemptContextDTO,
        *,
        worker_id: UUID,
        step: HumanSuspensionCleanupStep,
        require_pending: bool = True,
    ) -> tuple[DurableJobRow, HumanSuspensionObligationRow, str, HumanSuspensionJobFactsDTO]:
        # Current authorization locks and refreshes the original, child and attempt.
        facts = await self._authorizer.require_current(context, worker_id=worker_id)
        with self._session.no_autoflush:
            parent = await self._session.get(
                HumanSuspensionObligationRow, facts.binding.obligation_id.value
            )
            child = await self._session.get(DurableJobRow, facts.binding.job_id.value)
        if parent is None or child is None:
            raise ConflictError("The original suspension cleanup backing is unavailable.")

        if (
            require_pending
            and self._facts.step_states(parent)[step] is not IdentityRecoveryCleanupState.PENDING
        ):
            raise ConflictError("The original suspension cleanup step must still be pending.")

        # The closed step, checked attempt number and UUID fence fit the existing column.
        return child, parent, f"{step.value}:{facts.attempt}:{facts.fence.value}", facts

    @staticmethod
    def _set_step_state(
        parent: HumanSuspensionObligationRow,
        step: HumanSuspensionCleanupStep,
        state: IdentityRecoveryCleanupState,
    ) -> None:
        match step:
            case HumanSuspensionCleanupStep.KRATOS_SESSIONS:
                parent.kratos_sessions = state
            case HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS:
                parent.hydra_cli_grants = state
            case HumanSuspensionCleanupStep.HYDRA_REMEMBERED_LOGINS:
                parent.hydra_remembered_logins = state
