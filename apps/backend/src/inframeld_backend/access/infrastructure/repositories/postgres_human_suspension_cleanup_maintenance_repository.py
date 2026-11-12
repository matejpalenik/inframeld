from datetime import datetime
from typing import override
from uuid import UUID

from sqlalchemy import DateTime, String, exists, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.human_suspension_cleanup_maintenance_command import (
    HumanSuspensionCleanupMaintenanceCommand,
)
from inframeld_backend.access.application.dtos.human_suspension_cleanup_maintenance_result_dto import (
    HumanSuspensionCleanupMaintenanceResultDTO,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_continue_outcome import (
    HumanSuspensionCleanupContinueOutcome as Outcome,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_execution_state import (
    HumanSuspensionCleanupExecutionState as Execution,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_maintenance_error_code import (
    HumanSuspensionCleanupMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.enums.human_suspension_cleanup_maintenance_intent import (
    HumanSuspensionCleanupMaintenanceIntent as Intent,
)
from inframeld_backend.access.application.errors.human_suspension_cleanup_maintenance_error import (
    HumanSuspensionCleanupMaintenanceError,
)
from inframeld_backend.access.application.protocols.human_suspension_cleanup_maintenance_repository import (
    HumanSuspensionCleanupMaintenanceRepository,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.shared.application.enums.human_suspension_cleanup_step import (
    HumanSuspensionCleanupStep,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
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
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresHumanSuspensionCleanupMaintenanceRepository(
    HumanSuspensionCleanupMaintenanceRepository
):
    """Use the retained original and common receipt as the only local authority."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._facts = PostgresHumanSuspensionJobFactsReader(session)

    @override
    async def execute(
        self, *, command: HumanSuspensionCleanupMaintenanceCommand
    ) -> HumanSuspensionCleanupMaintenanceResultDTO:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Suspension maintenance requires an active transaction.")
        with self._session.no_autoflush:
            return await self._execute(command)

    async def _execute(
        self, command: HumanSuspensionCleanupMaintenanceCommand
    ) -> HumanSuspensionCleanupMaintenanceResultDTO:
        installing = select(InstallationIdentityRow.installation_id).where(
            InstallationIdentityRow.singleton_key == 1
        )
        if command.intent is Intent.CONTINUE:
            isolation = await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            if isolation != "read committed":
                raise RuntimeError("Suspension continuation requires READ COMMITTED isolation.")
            installing = installing.with_for_update(read=True, key_share=True)
        installed = await self._session.scalar(installing)
        if installed is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")
        if installed != command.expected_installation_id.value:
            raise HumanSuspensionCleanupMaintenanceError(Code.INSTALLATION_MISMATCH)

        original_id = self._original_id(command)
        if command.intent is Intent.INSPECT:
            if original_id is None:
                raise HumanSuspensionCleanupMaintenanceError(Code.NOT_FOUND)
            return await self._inspect(command, original_id)
        return await self._continue_original(command, original_id)

    async def _inspect(
        self, command: HumanSuspensionCleanupMaintenanceCommand, original_id: UUID
    ) -> HumanSuspensionCleanupMaintenanceResultDTO:
        parent, child = HumanSuspensionObligationRow, DurableJobRow
        snapshot = (
            await self._session.execute(
                select(parent, child, func.clock_timestamp(type_=DateTime(timezone=True)))
                .outerjoin(child, child.id == parent.job_id)
                .where(
                    parent.id == original_id,
                    parent.installation_id == command.expected_installation_id.value,
                )
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if snapshot is None:
            raise HumanSuspensionCleanupMaintenanceError(Code.NOT_FOUND)
        original, job, now = snapshot
        if job is not None and not self._facts.matches_child(original, job):
            job = None
        states = self._facts.step_states(original)
        marker = (
            self._facts.decode_marker(job)
            if job is not None and job.work_deadline is not None
            else None
        )
        if marker is not None:
            step, _, _ = marker
            if states[step] is IdentityRecoveryCleanupState.PENDING:
                states[step] = IdentityRecoveryCleanupState.UNCERTAIN
        return HumanSuspensionCleanupMaintenanceResultDTO(
            command.operation_id,
            command.expected_installation_id,
            command.cleanup_operation_id,
            self._execution(original, job, now),
            states[HumanSuspensionCleanupStep.KRATOS_SESSIONS],
            states[HumanSuspensionCleanupStep.HYDRA_CLI_GRANTS],
            states[HumanSuspensionCleanupStep.HYDRA_REMEMBERED_LOGINS],
        )

    async def _continue_original(
        self, command: HumanSuspensionCleanupMaintenanceCommand, original_id: UUID | None
    ) -> HumanSuspensionCleanupMaintenanceResultDTO:
        original = (
            await self._session.get(
                HumanSuspensionObligationRow, original_id, populate_existing=True
            )
            if original_id is not None
            else None
        )
        receipt = await self._receipt(command)
        if receipt is not None:
            return self._replay(command, receipt, original)
        if original is None or original.installation_id != command.expected_installation_id.value:
            raise HumanSuspensionCleanupMaintenanceError(Code.NOT_FOUND)

        binding = PostgresJobBindingMapper.human_suspension(original)
        parent = await self._facts.lock_retained_original(binding)
        if parent is None:
            raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)
        receipt = await self._receipt(command)
        if receipt is not None:
            return self._replay(command, receipt, parent)
        if not await self._facts.has_current_target(
            binding, allow_restored=parent.completed_at is not None
        ):
            raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)

        repeat = None
        job = None
        if parent.completed_at is not None:
            now = await self._now()
            outcome = Outcome.ALREADY_COMPLETE
        else:
            job = await self._facts.lock_child(parent)
            if job is None or job.cancel_requested:
                raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)
            opened = (
                await self._facts.lock_open_attempt(job)
                if job.status == JobStatus.RUNNING.value
                else None
            )
            now = await self._now()
            execution = self._execution(parent, job, now)
            if (
                execution is Execution.RUNNING and opened is not None and opened.started_at <= now
            ) or (execution is Execution.QUEUED and await self._queued_is_coherent(parent, job)):
                outcome = Outcome.ALREADY_SCHEDULED
            elif execution is Execution.STOPPED:
                repeat = await self._repeat_for_stopped(parent, job, now)
                outcome = Outcome.REQUEUED
            else:
                raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)

        accepted = await self._record(command, parent, outcome, now, repeat)
        if not accepted:
            winner = await self._receipt(command)
            if winner is None:
                raise DependencyUnavailableError("The maintenance receipt is unavailable.")
            return self._replay(command, winner, parent)
        if job is not None:
            committed_clock = await self._now()
            if repeat is not None:
                if job.work_deadline is None or committed_clock >= min(
                    job.queued_deadline, job.work_deadline
                ):
                    raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)
                job.status = JobStatus.QUEUED.value
                job.terminal_at = None
                await self._session.flush()
            elif self._execution(parent, job, committed_clock) not in (
                Execution.QUEUED,
                Execution.RUNNING,
            ):
                raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)
        return self._result(command, outcome)

    async def _queued_is_coherent(
        self, parent: HumanSuspensionObligationRow, job: DurableJobRow
    ) -> bool:
        if job.pending_effect is not None:
            return await self._facts.lock_unused_repeat(parent, job) is not None
        if job.attempt_count == 0:
            return True
        attempt = await self._session.get(
            DurableJobAttemptRow,
            (job.id, job.attempt_count),
            populate_existing=True,
            with_for_update=True,
        )
        return attempt is not None and attempt.ended_at is not None

    async def _repeat_for_stopped(
        self, parent: HumanSuspensionObligationRow, job: DurableJobRow, now: datetime
    ) -> tuple[HumanSuspensionCleanupStep, DurableJobAttemptRow]:
        if (
            job.status != JobStatus.RECOVERY_REQUIRED.value
            or job.reason != "provider_outcome_uncertain"
            or job.worker_id is not None
            or job.fence is not None
            or job.lease_expires_at is not None
            or job.work_deadline is None
            or not 1 <= job.attempt_count < 3
            or not job.admitted_at <= job.due_at < min(job.queued_deadline, job.work_deadline)
            or not job.admitted_at <= now < min(job.queued_deadline, job.work_deadline)
        ):
            raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)
        marker = await self._facts.lock_ended_marker(job)
        if marker is None:
            raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)
        step, attempt = marker
        receipt = HostMaintenanceReceiptRow
        if (
            attempt.number != job.attempt_count
            or attempt.ended_at != job.terminal_at
            or self._facts.step_states(parent)[step] is IdentityRecoveryCleanupState.CONFIRMED
            or await self._session.scalar(
                select(
                    exists().where(
                        receipt.suspension_obligation_id == parent.id,
                        receipt.suspension_repeat_step.is_not(None),
                    )
                )
            )
        ):
            raise HumanSuspensionCleanupMaintenanceError(Code.NOT_CONTINUABLE)
        return marker

    async def _receipt(
        self, command: HumanSuspensionCleanupMaintenanceCommand
    ) -> HostMaintenanceReceiptRow | None:
        return await self._session.get(
            HostMaintenanceReceiptRow,
            (command.expected_installation_id.value, command.operation_id.value),
            populate_existing=True,
        )

    async def _record(
        self,
        command: HumanSuspensionCleanupMaintenanceCommand,
        parent: HumanSuspensionObligationRow,
        outcome: Outcome,
        now: datetime,
        repeat: tuple[HumanSuspensionCleanupStep, DurableJobAttemptRow] | None,
    ) -> bool:
        r = HostMaintenanceReceiptRow
        inserted = await self._session.scalar(
            insert(r)
            .values(
                installation_id=parent.installation_id,
                operator_request_id=command.operation_id.value,
                mode="human-suspension-cleanup",
                authority=parent.authority,
                subject=parent.subject,
                operator_label=command.operator_label,
                reason=command.reason,
                authorized_at=now,
                outcome=outcome.value,
                suspension_obligation_id=parent.id,
                suspension_repeat_step=repeat[0].value if repeat else None,
                suspension_repeat_attempt=repeat[1].number if repeat else None,
                suspension_repeat_fence=repeat[1].fence if repeat else None,
            )
            .on_conflict_do_nothing(index_elements=[r.installation_id, r.operator_request_id])
            .returning(r.operator_request_id)
        )
        return inserted is not None

    @staticmethod
    def _replay(
        command: HumanSuspensionCleanupMaintenanceCommand,
        receipt: HostMaintenanceReceiptRow,
        parent: HumanSuspensionObligationRow | None,
    ) -> HumanSuspensionCleanupMaintenanceResultDTO:
        if parent is None or (
            receipt.mode,
            receipt.suspension_obligation_id,
            receipt.installation_id,
            receipt.authority,
            receipt.subject,
            receipt.operator_label,
            receipt.reason,
        ) != (
            "human-suspension-cleanup",
            parent.id,
            parent.installation_id,
            parent.authority,
            parent.subject,
            command.operator_label,
            command.reason,
        ):
            raise HumanSuspensionCleanupMaintenanceError(Code.KEY_REUSED)
        return PostgresHumanSuspensionCleanupMaintenanceRepository._result(
            command, Outcome(receipt.outcome)
        )

    @staticmethod
    def _result(
        command: HumanSuspensionCleanupMaintenanceCommand, outcome: Outcome
    ) -> HumanSuspensionCleanupMaintenanceResultDTO:
        return HumanSuspensionCleanupMaintenanceResultDTO(
            command.operation_id,
            command.expected_installation_id,
            command.cleanup_operation_id,
            outcome,
        )

    @staticmethod
    def _original_id(command: HumanSuspensionCleanupMaintenanceCommand) -> UUID | None:
        try:
            original = UUID(command.cleanup_operation_id.value)
            if str(original) == command.cleanup_operation_id.value:
                return original
        except ValueError:
            pass
        return None

    @staticmethod
    def _execution(
        parent: HumanSuspensionObligationRow, job: DurableJobRow | None, now: datetime
    ) -> Execution:
        if parent.completed_at is not None:
            return Execution.COMPLETED
        if parent.queue_exhausted_at is not None:
            return Execution.EXHAUSTED
        if job is not None and (
            job.status == JobStatus.RUNNING.value
            and not job.cancel_requested
            and job.worker_id is not None
            and job.fence is not None
            and job.lease_expires_at is not None
            and job.work_deadline is not None
            and now < job.lease_expires_at <= job.work_deadline
            and 1 <= job.attempt_count <= 3
        ):
            return Execution.RUNNING
        if now >= parent.queued_deadline or (
            job is not None
            and (
                job.attempt_count >= 3
                or (job.work_deadline is not None and now >= job.work_deadline)
                or (
                    job.status == JobStatus.QUEUED.value
                    and (
                        job.due_at >= job.queued_deadline
                        or (job.work_deadline is not None and job.due_at >= job.work_deadline)
                    )
                )
            )
        ):
            return Execution.EXHAUSTED
        if job is not None and (
            job.status == JobStatus.QUEUED.value
            and not job.cancel_requested
            and job.worker_id is None
            and job.fence is None
            and job.lease_expires_at is None
            and job.terminal_at is None
            and 0 <= job.attempt_count < 3
            and (job.attempt_count == 0) == (job.work_deadline is None)
            and job.admitted_at <= now
            and job.admitted_at <= job.due_at
        ):
            return Execution.QUEUED
        return Execution.STOPPED

    async def _now(self) -> datetime:
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise DependencyUnavailableError("The authoritative database clock is unavailable.")
        return now
