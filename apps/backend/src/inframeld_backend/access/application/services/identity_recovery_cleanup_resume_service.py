import asyncio
from datetime import UTC, datetime
from typing import override
from uuid import uuid4

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_facts_dto import (
    IdentityRecoveryCleanupResumeFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_maintenance_receipt_dto import (
    IdentityRecoveryMaintenanceReceiptDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_resume_outcome import (
    IdentityRecoveryCleanupResumeOutcome as Outcome,
)
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.application.enums.recovery_maintenance_error_code import (
    RecoveryMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.enums.recovery_maintenance_mode import (
    RecoveryMaintenanceMode,
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
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_resumer import (
    IdentityRecoveryCleanupResumer,
)
from inframeld_backend.access.application.protocols.identity_recovery_completion_facts_reader import (
    IdentityRecoveryCompletionFactsReader,
)
from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState as State,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.transaction_manager import TransactionManager


class IdentityRecoveryCleanupResumeService(IdentityRecoveryCleanupResumer):
    """Coordinate host authorization in one bounded database transaction.

    The worker performs provider cleanup and the normal completion checks.
    """

    def __init__(
        self,
        transactions: TransactionManager,
        facts: IdentityRecoveryCleanupResumeFactsReader,
        coordination: IdentityRecoveryCompletionFactsReader,
        writer: IdentityRecoveryCleanupResumeWriter,
    ) -> None:
        self._transactions = transactions
        self._facts = facts
        self._coordination = coordination
        self._writer = writer

    @override
    async def resume(
        self, *, command: ResumeIdentityRecoveryCleanupCommand
    ) -> IdentityRecoveryCleanupResumeResultDTO:
        try:
            async with asyncio.timeout(5):
                async with self._transactions.begin():
                    return await self._resume(command)
        except TimeoutError:
            raise DependencyUnavailableError(
                "Recovery maintenance exceeded its database deadline."
            ) from None

    async def _resume(
        self, command: ResumeIdentityRecoveryCleanupCommand
    ) -> IdentityRecoveryCleanupResumeResultDTO:
        installed = await self._facts.installation()
        if installed is None:
            raise RecoveryMaintenanceError(Code.DEPENDENCY_UNAVAILABLE)

        if installed != command.expected_installation_id:
            raise RecoveryMaintenanceError(Code.INSTALLATION_MISMATCH)

        recorded = await self._facts.receipt(
            installation_id=installed, operation_id=command.operation_id
        )
        if recorded is not None:
            return self._replay(command, recorded)

        original = await self._facts.original(
            installation_id=installed, operation_id=command.recovery_operation_id
        )
        if original is None:
            raise RecoveryMaintenanceError(Code.NOT_FOUND)

        coordinated = await self._coordination.read(
            installation_id=installed,
            authority=original.event.identity.authority,
            flow_id=original.event.flow_id,
        )
        if coordinated.installation_id != installed or coordinated.admission != original:
            raise RuntimeError("Recovery maintenance facts changed their original binding.")

        # A same-identity request may have committed while this request waited.
        recorded = await self._facts.receipt(
            installation_id=installed, operation_id=command.operation_id
        )
        if recorded is not None:
            return self._replay(command, recorded)

        facts = await self._facts.read(installation_id=installed, admission=original)
        now = datetime.now(UTC)
        outcome = self._outcome(facts)
        terminal_reason = None
        if outcome is not Outcome.ALREADY_COMPLETED and coordinated.credential_version is None:
            raise RecoveryMaintenanceError(Code.DEPENDENCY_UNAVAILABLE)

        if outcome is Outcome.AUTHORIZED:
            work = facts.work
            if (
                work is None
                or not work.has_original_password_receipt
                or facts.kratos_cleanup_state is not State.CONFIRMED
            ):
                raise RecoveryMaintenanceError(Code.EVIDENCE_MISSING)
            self._require_work_binding(work, command)
            terminal_reason = self._terminal_reason(work, now)

        run_id = uuid4() if outcome is Outcome.AUTHORIZED else None
        budget = IdentityRecoveryCleanupRunBudget(now) if run_id is not None else None
        result = IdentityRecoveryCleanupResumeResultDTO(
            command.operation_id,
            installed,
            command.recovery_operation_id,
            outcome,
            facts.released_at is not None,
            run_id,
            None if budget is None else budget.deadline,
        )
        receipt = IdentityRecoveryMaintenanceReceiptDTO(command, now, result)

        if not await self._writer.record(receipt):
            winner = await self._facts.receipt(
                installation_id=installed, operation_id=command.operation_id
            )
            if winner is None:
                raise RuntimeError("The winning maintenance receipt is unavailable.")
            return self._replay(command, winner)

        if (
            outcome is Outcome.CLEANUP_CONFIRMED
            and not facts.has_complete_proof
            and facts.work is not None
        ):
            work = facts.work
            if (
                not work.has_original_password_receipt
                or work.kratos_cleanup_state is not State.CONFIRMED
            ):
                raise RecoveryMaintenanceError(Code.EVIDENCE_MISSING)
            self._require_work_binding(work, command)
            await self._writer.save_complete_proof(work, at=now)
            if work.run.ended_at is None:
                await self._writer.settle(work, at=now, terminal_reason="cleanup_confirmed")

        if outcome is Outcome.AUTHORIZED:
            if terminal_reason is not None and facts.work is not None:
                await self._writer.settle(facts.work, at=now, terminal_reason=terminal_reason)
            await self._writer.authorize_run(receipt)

        return result

    @staticmethod
    def _replay(
        command: ResumeIdentityRecoveryCleanupCommand,
        receipt: IdentityRecoveryMaintenanceReceiptDTO,
    ) -> IdentityRecoveryCleanupResumeResultDTO:
        if (
            receipt.mode is not RecoveryMaintenanceMode.RESUME_RECOVERY_CLEANUP
            or receipt.command != command
        ):
            raise RecoveryMaintenanceError(Code.KEY_REUSED)

        return receipt.result

    @staticmethod
    def _outcome(facts: IdentityRecoveryCleanupResumeFactsDTO) -> Outcome:
        if facts.released_at is not None:
            return Outcome.ALREADY_COMPLETED

        if facts.has_complete_proof:
            return Outcome.CLEANUP_CONFIRMED

        if (
            facts.work is not None
            and facts.work.cli_grants_state is facts.work.remembered_logins_state is State.CONFIRMED
        ):
            return Outcome.CLEANUP_CONFIRMED

        if facts.hydra_cleanup_state is State.CONFIRMED:
            if facts.kratos_cleanup_state is State.CONFIRMED:
                return Outcome.CLEANUP_CONFIRMED
            raise RecoveryMaintenanceError(Code.EVIDENCE_MISSING)

        return Outcome.AUTHORIZED

    @staticmethod
    def _require_work_binding(
        work: IdentityRecoveryCleanupWorkDTO, command: ResumeIdentityRecoveryCleanupCommand
    ) -> None:
        if (
            work.installation_id != command.expected_installation_id
            or work.admission.operation_id != command.recovery_operation_id
        ):
            raise RuntimeError("Cleanup observations do not match the requested original.")

        budget = IdentityRecoveryCleanupRunBudget(work.run.authorized_at)
        if work.run.deadline != budget.deadline or work.run.max_attempts != budget.max_attempts:
            raise RuntimeError("The original cleanup budget is inconsistent.")

    @staticmethod
    def _terminal_reason(work: IdentityRecoveryCleanupWorkDTO, now: datetime) -> str | None:
        if work.run.ended_at is not None:
            if work.claim is not None:
                raise RuntimeError("An ended run retains execution ownership.")
            return None

        permanent = next(
            (
                step.outcome
                for step in work.steps
                if step.outcome is not None
                and step.outcome.disposition is OAuthCleanupDisposition.OPERATOR_REQUIRED
            ),
            None,
        )
        if permanent is not None:
            return (
                "permanent_provider_rejection"
                if permanent.state is State.FAILED
                else "provider_protocol_error"
            )
        if now >= work.run.deadline:
            return "deadline_exhausted"

        live_attempt = work.claim is not None and work.claim.lease_expires_at > now
        if work.run.consumed_attempts >= work.run.max_attempts and not live_attempt:
            return "attempt_budget_exhausted"

        raise RecoveryMaintenanceError(Code.RUN_ACTIVE)
