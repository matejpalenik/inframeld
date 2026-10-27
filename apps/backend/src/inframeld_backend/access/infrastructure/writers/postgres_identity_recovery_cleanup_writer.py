from datetime import datetime
from typing import override

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.human_oauth_cleanup_outcome_dto import (
    HumanOAuthCleanupOutcomeDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_claim_dto import (
    IdentityRecoveryCleanupClaimDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_step import (
    IdentityRecoveryCleanupStep,
)
from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_writer import (
    IdentityRecoveryCleanupWriter,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_attempt_row import (
    IdentityRecoveryCleanupAttemptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_proof_row import (
    IdentityRecoveryCleanupProofRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_step_row import (
    IdentityRecoveryCleanupStepRow,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresIdentityRecoveryCleanupWriter(IdentityRecoveryCleanupWriter):
    """Keep fenced checkpoints on the coordinated operation-local session."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
    ) -> None:
        self._session = session
        self._installation_id = installation_id
        self._authority = authority

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Cleanup persistence requires an active transaction.")

    async def _job(self, operation_id: str) -> IdentityRecoveryCleanupJobRow:
        self._require_transaction()
        job = await self._session.scalar(
            select(IdentityRecoveryCleanupJobRow)
            .where(
                IdentityRecoveryCleanupJobRow.operation_id == operation_id,
                IdentityRecoveryCleanupJobRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupJobRow.authority == self._authority.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None:
            raise ConflictError("The original cleanup job is unavailable.")
        return job

    async def _owner(
        self, claim: IdentityRecoveryCleanupClaimDTO, *, at: datetime
    ) -> IdentityRecoveryCleanupJobRow:
        job = await self._job(claim.operation_id.value)
        if (job.active_attempt_id, job.worker_id, job.ownership_token, job.lease_expires_at) != (
            claim.attempt_id,
            claim.worker_id,
            claim.token,
            claim.lease_expires_at,
        ) or claim.lease_expires_at <= at:
            raise ConflictError("Recovery execution ownership changed.")
        run = await self._session.get(
            IdentityRecoveryCleanupRunRow, claim.run_id, populate_existing=True
        )
        if run is None or run.ended_at is not None or run.operation_id != job.operation_id:
            raise ConflictError("The recovery cleanup run has ended.")
        return job

    @override
    async def claim(
        self,
        work: IdentityRecoveryCleanupWorkDTO,
        claim: IdentityRecoveryCleanupClaimDTO,
        *,
        at: datetime,
    ) -> None:
        job = await self._job(work.admission.operation_id.value)
        if (
            job.ownership_token is not None
            or claim.operation_id != work.admission.operation_id
            or claim.run_id != work.run.id
        ):
            raise ConflictError("The recovery cleanup job is already claimed.")

        changed = await self._session.scalar(
            update(IdentityRecoveryCleanupRunRow)
            .where(
                IdentityRecoveryCleanupRunRow.id == work.run.id,
                IdentityRecoveryCleanupRunRow.operation_id == job.operation_id,
                IdentityRecoveryCleanupRunRow.ended_at.is_(None),
                IdentityRecoveryCleanupRunRow.consumed_attempts == work.run.consumed_attempts,
                IdentityRecoveryCleanupRunRow.consumed_attempts
                < IdentityRecoveryCleanupRunRow.max_attempts,
                IdentityRecoveryCleanupRunRow.next_attempt_at <= at,
                IdentityRecoveryCleanupRunRow.deadline > at,
            )
            .values(consumed_attempts=work.run.consumed_attempts + 1)
            .returning(IdentityRecoveryCleanupRunRow.id)
        )
        if changed is None:
            raise ConflictError("The recovery cleanup budget changed.")

        await self._session.execute(
            insert(IdentityRecoveryCleanupAttemptRow).values(
                id=claim.attempt_id,
                operation_id=job.operation_id,
                run_id=work.run.id,
                ordinal=work.run.consumed_attempts + 1,
                worker_id=claim.worker_id,
                ownership_token=claim.token,
                claimed_at=at,
                lease_expires_at=claim.lease_expires_at,
            )
        )
        await self._session.execute(
            update(IdentityRecoveryCleanupJobRow)
            .where(IdentityRecoveryCleanupJobRow.operation_id == job.operation_id)
            .values(
                active_attempt_id=claim.attempt_id,
                worker_id=claim.worker_id,
                ownership_token=claim.token,
                lease_expires_at=claim.lease_expires_at,
            )
        )

    @override
    async def admit_step(
        self,
        claim: IdentityRecoveryCleanupClaimDTO,
        step: IdentityRecoveryCleanupStep,
        *,
        at: datetime,
    ) -> None:
        job = await self._owner(claim, at=at)
        run = await self._session.get(IdentityRecoveryCleanupRunRow, claim.run_id)
        if run is None or at >= run.deadline:
            raise ConflictError("The recovery dispatch deadline has elapsed.")
        state = (
            job.cli_grants_state
            if step is IdentityRecoveryCleanupStep.CLI_GRANTS
            else job.remembered_logins_state
        )
        if state is IdentityRecoveryCleanupState.CONFIRMED:
            raise RuntimeError("Confirmed cleanup cannot be dispatched again.")
        await self._session.execute(
            insert(IdentityRecoveryCleanupStepRow).values(
                attempt_id=claim.attempt_id,
                operation_id=job.operation_id,
                step=step,
                dispatched_at=at,
            )
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
        job = await self._owner(claim, at=at)
        changed = await self._session.scalar(
            update(IdentityRecoveryCleanupStepRow)
            .where(
                IdentityRecoveryCleanupStepRow.attempt_id == claim.attempt_id,
                IdentityRecoveryCleanupStepRow.step == step,
                IdentityRecoveryCleanupStepRow.checkpointed_at.is_(None),
            )
            .values(
                checkpointed_at=at,
                state=outcome.state,
                disposition=outcome.disposition,
                category=outcome.category,
                http_status=outcome.http_status,
                retry_after_seconds=outcome.retry_after_seconds,
            )
            .returning(IdentityRecoveryCleanupStepRow.attempt_id)
        )
        if changed is None:
            raise ConflictError("The provider step has no unfinished dispatch.")

        if step is IdentityRecoveryCleanupStep.CLI_GRANTS:
            if job.cli_grants_state is IdentityRecoveryCleanupState.CONFIRMED:
                raise ConflictError("Confirmed cleanup cannot regress.")
            job.cli_grants_state = outcome.state
            if outcome.state is IdentityRecoveryCleanupState.CONFIRMED:
                job.cli_confirmation_attempt_id = claim.attempt_id
        else:
            if job.remembered_logins_state is IdentityRecoveryCleanupState.CONFIRMED:
                raise ConflictError("Confirmed cleanup cannot regress.")
            job.remembered_logins_state = outcome.state
            if outcome.state is IdentityRecoveryCleanupState.CONFIRMED:
                job.login_confirmation_attempt_id = claim.attempt_id
        await self._session.flush()

    @override
    async def finish(
        self,
        work: IdentityRecoveryCleanupWorkDTO,
        *,
        at: datetime,
        terminal_reason: str | None,
        next_attempt_at: datetime | None = None,
    ) -> None:
        job = await self._job(work.admission.operation_id.value)
        expected_token = None if work.claim is None else work.claim.token
        if job.ownership_token != expected_token:
            raise ConflictError("Recovery execution ownership changed.")

        if work.claim is not None:
            # Missing acknowledgement after a crash is uncertainty, never failure or success.
            await self._session.execute(
                update(IdentityRecoveryCleanupStepRow)
                .where(
                    IdentityRecoveryCleanupStepRow.attempt_id == work.claim.attempt_id,
                    IdentityRecoveryCleanupStepRow.checkpointed_at.is_(None),
                )
                .values(
                    checkpointed_at=at,
                    state=IdentityRecoveryCleanupState.UNCERTAIN,
                    disposition=OAuthCleanupDisposition.RETRYABLE,
                    category=OAuthCleanupCategory.TRANSPORT_FAILURE,
                )
            )
            await self._session.execute(
                update(IdentityRecoveryCleanupAttemptRow)
                .where(
                    IdentityRecoveryCleanupAttemptRow.id == work.claim.attempt_id,
                    IdentityRecoveryCleanupAttemptRow.ended_at.is_(None),
                )
                .values(ended_at=at, terminal_reason=terminal_reason or "retry_scheduled")
            )

        run = await self._session.get(
            IdentityRecoveryCleanupRunRow, work.run.id, populate_existing=True
        )
        if run is None or run.ended_at is not None:
            raise ConflictError("The recovery cleanup run has ended.")
        if terminal_reason is None:
            if next_attempt_at is None or not at < next_attempt_at < run.deadline:
                raise RuntimeError("A retry requires its checked next-attempt time.")
            run.next_attempt_at = next_attempt_at
        else:
            run.ended_at = at
            run.terminal_reason = terminal_reason

        job.active_attempt_id = None
        job.worker_id = None
        job.ownership_token = None
        job.lease_expires_at = None
        await self._session.flush()

    @override
    async def save_complete_proof(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime
    ) -> None:
        await self._job(work.admission.operation_id.value)
        if work.cli_confirmation_attempt_id is None or work.login_confirmation_attempt_id is None:
            raise RuntimeError("Complete cleanup requires saved confirmation provenance.")

        for step, attempt_id in (
            (IdentityRecoveryCleanupStep.CLI_GRANTS, work.cli_confirmation_attempt_id),
            (IdentityRecoveryCleanupStep.REMEMBERED_LOGINS, work.login_confirmation_attempt_id),
        ):
            confirmed = await self._session.scalar(
                select(IdentityRecoveryCleanupStepRow.attempt_id).where(
                    IdentityRecoveryCleanupStepRow.attempt_id == attempt_id,
                    IdentityRecoveryCleanupStepRow.operation_id
                    == work.admission.operation_id.value,
                    IdentityRecoveryCleanupStepRow.step == step,
                    IdentityRecoveryCleanupStepRow.state == IdentityRecoveryCleanupState.CONFIRMED,
                )
            )
            if confirmed is None:
                raise RuntimeError("The original provider confirmation is unavailable.")

        await self._session.execute(
            insert(IdentityRecoveryCleanupProofRow)
            .values(
                operation_id=work.admission.operation_id.value,
                installation_id=work.installation_id.value,
                authority=work.admission.event.identity.authority.value,
                subject=work.admission.event.identity.subject.value,
                source_operation_id=work.admission.operation_id.value,
                source_receipt_id=work.evidence_receipt_id,
                cli_confirmation_attempt_id=work.cli_confirmation_attempt_id,
                login_confirmation_attempt_id=work.login_confirmation_attempt_id,
                recorded_at=at,
                reconcile_at=at,
            )
            .on_conflict_do_nothing()
        )
