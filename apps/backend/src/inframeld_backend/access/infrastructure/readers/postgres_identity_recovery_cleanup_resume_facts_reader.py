from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.resume_identity_recovery_cleanup_command import (
    ResumeIdentityRecoveryCleanupCommand,
)
from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_facts_dto import (
    IdentityRecoveryCleanupResumeFactsDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_resume_result_dto import (
    IdentityRecoveryCleanupResumeResultDTO,
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
    IdentityRecoveryCleanupResumeOutcome,
)
from inframeld_backend.access.application.enums.recovery_maintenance_mode import (
    RecoveryMaintenanceMode,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_resume_facts_reader import (
    IdentityRecoveryCleanupResumeFactsReader,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.mappers.postgres_identity_recovery_cleanup_work_mapper import (
    PostgresIdentityRecoveryCleanupWorkMapper,
)
from inframeld_backend.access.infrastructure.readers.identity_recovery_cleanup_work_queries import (
    IdentityRecoveryCleanupWorkQueries,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_proof_row import (
    IdentityRecoveryCleanupProofRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_step_row import (
    IdentityRecoveryCleanupStepRow,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresIdentityRecoveryCleanupResumeFactsReader(IdentityRecoveryCleanupResumeFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Recovery maintenance requires an active transaction.")

    @override
    async def installation(self) -> InstallationId | None:
        self._require_transaction()
        value = await self._session.scalar(
            select(InstallationIdentityRow.installation_id)
            .where(InstallationIdentityRow.singleton_key == 1)
            .execution_options(autoflush=False)
        )
        return None if value is None else InstallationId(value)

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> IdentityRecoveryMaintenanceReceiptDTO | None:
        self._require_transaction()
        row = await self._session.get(
            HostMaintenanceReceiptRow,
            (installation_id.value, operation_id.value),
            populate_existing=True,
        )
        if row is None:
            return None

        mode = RecoveryMaintenanceMode(row.mode)
        command = ResumeIdentityRecoveryCleanupCommand(
            installation_id,
            operation_id,
            OperationId(row.recovery_operation_id),
            row.operator_label,
            row.reason,
        )
        result = IdentityRecoveryCleanupResumeResultDTO(
            operation_id,
            installation_id,
            command.recovery_operation_id,
            IdentityRecoveryCleanupResumeOutcome(row.outcome),
            row.released,
            row.run_id,
            row.deadline,
        )
        return IdentityRecoveryMaintenanceReceiptDTO(command, row.authorized_at, result, mode)

    @override
    async def original(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> IdentityRecoveryAdmissionDTO | None:
        self._require_transaction()
        row = await self._session.scalar(
            select(IdentityRecoveryAdmissionRow)
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation_id.value,
                IdentityRecoveryAdmissionRow.operation_id == operation_id.value,
            )
            .execution_options(populate_existing=True, autoflush=False)
        )
        if row is None:
            return None
        return IdentityRecoveryAdmissionDTO(
            IdentityRecoveryEventDTO(
                IdentityRecoveryFlowId(row.flow_id),
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(row.authority), IdentitySubject(row.subject)
                ),
                row.event_kind,
            ),
            operation_id,
        )

    @override
    async def read(
        self, *, installation_id: InstallationId, admission: IdentityRecoveryAdmissionDTO
    ) -> IdentityRecoveryCleanupResumeFactsDTO:
        self._require_transaction()
        row = await self._session.get(
            IdentityRecoveryAdmissionRow, admission.operation_id.value, populate_existing=True
        )
        if row is None or (
            row.installation_id,
            row.authority,
            row.subject,
            row.flow_id,
            row.event_kind,
        ) != (
            installation_id.value,
            admission.event.identity.authority.value,
            admission.event.identity.subject.value,
            admission.event.flow_id.value,
            admission.event.event_kind,
        ):
            raise RuntimeError("The coordinated recovery binding changed.")

        proof = await self._session.get(
            IdentityRecoveryCleanupProofRow, admission.operation_id.value, populate_existing=True
        )
        if proof is not None and (proof.installation_id, proof.authority, proof.subject) != (
            row.installation_id,
            row.authority,
            row.subject,
        ):
            raise RuntimeError("The saved cleanup proof has a different identity.")

        statement = IdentityRecoveryCleanupWorkQueries.statement(
            installation_id=installation_id,
            identity=admission.event.identity,
            operation_id=admission.operation_id,
            include_ended=True,
            skip_locked=False,
        )
        result = (await self._session.execute(statement)).one_or_none()
        work = None
        if result is not None:
            job, run, original, receipt, version = result
            steps = ()
            if job.active_attempt_id is not None:
                stored = await self._session.scalars(
                    select(IdentityRecoveryCleanupStepRow)
                    .where(IdentityRecoveryCleanupStepRow.attempt_id == job.active_attempt_id)
                    .execution_options(populate_existing=True)
                )
                steps = tuple(
                    PostgresIdentityRecoveryCleanupWorkMapper.step(step) for step in stored
                )
            work = PostgresIdentityRecoveryCleanupWorkMapper.from_rows(
                installation_id, job, run, original, receipt, version, steps
            )
            if work.admission != admission:
                raise RuntimeError("Cleanup observations changed their original binding.")

        return IdentityRecoveryCleanupResumeFactsDTO(
            row.released_at,
            row.kratos_cleanup_state,
            row.hydra_cleanup_state,
            proof is not None,
            work,
        )
