from datetime import datetime
from typing import override

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_maintenance_receipt_dto import (
    IdentityRecoveryMaintenanceReceiptDTO,
)
from inframeld_backend.access.application.enums.identity_recovery_cleanup_resume_outcome import (
    IdentityRecoveryCleanupResumeOutcome,
)
from inframeld_backend.access.application.enums.identity_recovery_run_source import (
    IdentityRecoveryRunSource,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_resume_writer import (
    IdentityRecoveryCleanupResumeWriter,
)
from inframeld_backend.access.application.value_objects.identity_recovery_cleanup_run_budget import (
    IdentityRecoveryCleanupRunBudget,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.writers.postgres_identity_recovery_cleanup_writer import (
    PostgresIdentityRecoveryCleanupWriter,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError


class PostgresIdentityRecoveryCleanupResumeWriter(IdentityRecoveryCleanupResumeWriter):
    """Persist the receipt before run changes in the coordinated caller transaction.

    Only the optional run foreign key is deferred. The request key arbitrates
    concurrent authorizations immediately, including different recovery targets.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Maintenance persistence requires an active transaction.")

    @override
    async def record(self, receipt: IdentityRecoveryMaintenanceReceiptDTO) -> bool:
        self._require_transaction()
        command = receipt.command
        admission = await self._session.get(
            IdentityRecoveryAdmissionRow,
            command.recovery_operation_id.value,
            populate_existing=True,
        )
        if admission is None or admission.installation_id != command.expected_installation_id.value:
            raise ConflictError("The original recovery is unavailable.")

        inserted = await self._session.scalar(
            insert(HostMaintenanceReceiptRow)
            .values(
                installation_id=command.expected_installation_id.value,
                operator_request_id=command.operation_id.value,
                mode=receipt.mode.value,
                authority=admission.authority,
                subject=admission.subject,
                recovery_operation_id=command.recovery_operation_id.value,
                operator_label=command.operator_label,
                reason=command.reason,
                authorized_at=receipt.authorized_at,
                outcome=receipt.result.outcome.value,
                released=receipt.result.released,
                run_id=receipt.result.run_id,
                deadline=receipt.result.deadline,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    HostMaintenanceReceiptRow.installation_id,
                    HostMaintenanceReceiptRow.operator_request_id,
                ]
            )
            .returning(HostMaintenanceReceiptRow.operator_request_id)
        )
        return inserted is not None

    @override
    async def authorize_run(self, receipt: IdentityRecoveryMaintenanceReceiptDTO) -> None:
        self._require_transaction()
        result = receipt.result
        if (
            result.outcome is not IdentityRecoveryCleanupResumeOutcome.AUTHORIZED
            or result.run_id is None
        ):
            raise RuntimeError("A new run requires its accepted authorization.")

        stored = await self._session.get(
            HostMaintenanceReceiptRow, (result.installation_id.value, result.operation_id.value)
        )
        if stored is None or (
            stored.run_id,
            stored.recovery_operation_id,
            stored.authorized_at,
            stored.deadline,
        ) != (
            result.run_id,
            result.recovery_operation_id.value,
            receipt.authorized_at,
            result.deadline,
        ):
            raise ConflictError("The run does not match its maintenance receipt.")

        job = await self._session.scalar(
            select(IdentityRecoveryCleanupJobRow)
            .where(
                IdentityRecoveryCleanupJobRow.operation_id == result.recovery_operation_id.value,
                IdentityRecoveryCleanupJobRow.installation_id == result.installation_id.value,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is None or job.ownership_token is not None:
            raise ConflictError("The original cleanup job is unavailable for another run.")

        budget = IdentityRecoveryCleanupRunBudget(receipt.authorized_at)
        if budget.deadline != result.deadline:
            raise RuntimeError("The run budget differs from its receipt.")

        await self._session.execute(
            insert(IdentityRecoveryCleanupRunRow).values(
                id=result.run_id,
                operation_id=result.recovery_operation_id.value,
                authorization_source=IdentityRecoveryRunSource.HOST_OPERATOR,
                authorized_at=budget.started_at,
                deadline=budget.deadline,
                next_attempt_at=budget.started_at,
                max_attempts=budget.max_attempts,
                consumed_attempts=0,
            )
        )

    @override
    async def settle(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime, terminal_reason: str
    ) -> None:
        self._require_transaction()
        await PostgresIdentityRecoveryCleanupWriter(
            self._session,
            installation_id=work.installation_id,
            authority=work.admission.event.identity.authority,
        ).finish(work, at=at, terminal_reason=terminal_reason)

    @override
    async def save_complete_proof(
        self, work: IdentityRecoveryCleanupWorkDTO, *, at: datetime
    ) -> None:
        self._require_transaction()
        await PostgresIdentityRecoveryCleanupWriter(
            self._session,
            installation_id=work.installation_id,
            authority=work.admission.event.identity.authority,
        ).save_complete_proof(work, at=at)
