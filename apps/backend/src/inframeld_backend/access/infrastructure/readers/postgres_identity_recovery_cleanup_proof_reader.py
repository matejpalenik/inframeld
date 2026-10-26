from typing import override

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_proof_dto import (
    IdentityRecoveryCleanupProofDTO,
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
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_proof_reader import (
    IdentityRecoveryCleanupProofReader,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_proof_row import (
    IdentityRecoveryCleanupProofRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_step_row import (
    IdentityRecoveryCleanupStepRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_evidence_receipt_row import (
    IdentityRecoveryEvidenceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_proof_link_row import (
    IdentityRecoveryProofLinkRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresIdentityRecoveryCleanupProofReader(IdentityRecoveryCleanupProofReader):
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

    async def _require_scope(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Cleanup proof observations require an active transaction.")
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id)
            .where(InstallationIdentityRow.singleton_key == 1)
            .execution_options(autoflush=False)
        )
        if installed != self._installation_id.value:
            raise DependencyUnavailableError("The installation identity is not available.")

    @override
    async def pending_operations(self, *, limit: int) -> tuple[OperationId, ...]:
        await self._require_scope()
        rows = await self._session.scalars(
            select(IdentityRecoveryCleanupProofRow.operation_id)
            .where(
                IdentityRecoveryCleanupProofRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupProofRow.authority == self._authority.value,
                IdentityRecoveryCleanupProofRow.reconcile_at <= func.now(),
                or_(
                    IdentityRecoveryCleanupProofRow.checked_at.is_(None),
                    IdentityRecoveryCleanupProofRow.propagation_complete.is_(False),
                ),
            )
            .order_by(
                IdentityRecoveryCleanupProofRow.reconcile_at,
                IdentityRecoveryCleanupProofRow.operation_id,
            )
            .limit(limit)
        )
        return tuple(OperationId(value) for value in rows)

    @override
    async def read_admission(self, operation_id: OperationId) -> IdentityRecoveryAdmissionDTO:
        await self._require_scope()
        row = await self._session.scalar(
            select(IdentityRecoveryAdmissionRow)
            .where(
                IdentityRecoveryAdmissionRow.operation_id == operation_id.value,
                IdentityRecoveryAdmissionRow.installation_id == self._installation_id.value,
                IdentityRecoveryAdmissionRow.authority == self._authority.value,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ResourceNotFoundError()
        return self._admission(row)

    @override
    async def read_proof(self, operation_id: OperationId) -> IdentityRecoveryCleanupProofDTO | None:
        await self._require_scope()
        source = aliased(IdentityRecoveryAdmissionRow)
        cli = (
            exists()
            .where(
                IdentityRecoveryCleanupStepRow.attempt_id
                == IdentityRecoveryCleanupProofRow.cli_confirmation_attempt_id,
                IdentityRecoveryCleanupStepRow.operation_id
                == IdentityRecoveryCleanupProofRow.source_operation_id,
                IdentityRecoveryCleanupStepRow.step == IdentityRecoveryCleanupStep.CLI_GRANTS,
                IdentityRecoveryCleanupStepRow.state == IdentityRecoveryCleanupState.CONFIRMED,
                IdentityRecoveryCleanupStepRow.checkpointed_at.is_not(None),
            )
            .correlate(IdentityRecoveryCleanupProofRow)
        )
        login = (
            exists()
            .where(
                IdentityRecoveryCleanupStepRow.attempt_id
                == IdentityRecoveryCleanupProofRow.login_confirmation_attempt_id,
                IdentityRecoveryCleanupStepRow.operation_id
                == IdentityRecoveryCleanupProofRow.source_operation_id,
                IdentityRecoveryCleanupStepRow.step
                == IdentityRecoveryCleanupStep.REMEMBERED_LOGINS,
                IdentityRecoveryCleanupStepRow.state == IdentityRecoveryCleanupState.CONFIRMED,
                IdentityRecoveryCleanupStepRow.checkpointed_at.is_not(None),
            )
            .correlate(IdentityRecoveryCleanupProofRow)
        )
        result = (
            await self._session.execute(
                select(
                    IdentityRecoveryCleanupProofRow,
                    IdentityRecoveryAdmissionRow,
                    source,
                    IdentityRecoveryEvidenceReceiptRow,
                    IdentityRecoveryCleanupJobRow,
                    cli,
                    login,
                )
                .select_from(IdentityRecoveryCleanupProofRow)
                .join(
                    IdentityRecoveryAdmissionRow,
                    IdentityRecoveryAdmissionRow.operation_id
                    == IdentityRecoveryCleanupProofRow.operation_id,
                )
                .join(
                    source,
                    source.operation_id == IdentityRecoveryCleanupProofRow.source_operation_id,
                )
                .join(
                    IdentityRecoveryEvidenceReceiptRow,
                    IdentityRecoveryEvidenceReceiptRow.id
                    == IdentityRecoveryCleanupProofRow.source_receipt_id,
                )
                .join(
                    IdentityRecoveryCleanupJobRow,
                    IdentityRecoveryCleanupJobRow.operation_id == source.operation_id,
                )
                .where(
                    IdentityRecoveryCleanupProofRow.operation_id == operation_id.value,
                    IdentityRecoveryCleanupProofRow.installation_id == self._installation_id.value,
                    IdentityRecoveryCleanupProofRow.authority == self._authority.value,
                )
                .execution_options(populate_existing=True)
            )
        ).one_or_none()
        if result is None:
            return None

        proof, admission, original_source, receipt, job, cli_confirmed, login_confirmed = result
        binding = (proof.installation_id, proof.authority, proof.subject)
        password = (
            (receipt.installation_id, receipt.authority, receipt.subject, receipt.operation_id)
            == (*binding, original_source.operation_id)
            and receipt.event_type is IdentityRecoveryEvidenceType.PASSWORD_SETTINGS_SAVED
            and job.evidence_receipt_id == receipt.id
        )
        return IdentityRecoveryCleanupProofDTO(
            self._installation_id,
            self._admission(admission),
            self._admission(original_source),
            receipt.id,
            proof.cli_confirmation_attempt_id,
            proof.login_confirmation_attempt_id,
            password,
            original_source.kratos_cleanup_state,
            cli_confirmed,
            login_confirmed,
            proof.checked_at,
            proof.propagation_complete,
        )

    @override
    async def linked_older(self, source: OperationId, *, limit: int) -> tuple[OperationId, ...]:
        await self._require_scope()
        rows = await self._session.scalars(
            select(IdentityRecoveryProofLinkRow.covered_operation_id)
            .where(
                IdentityRecoveryProofLinkRow.installation_id == self._installation_id.value,
                IdentityRecoveryProofLinkRow.authority == self._authority.value,
                IdentityRecoveryProofLinkRow.covering_operation_id == source.value,
                IdentityRecoveryProofLinkRow.reconciled_at.is_(None),
            )
            .order_by(
                IdentityRecoveryProofLinkRow.recorded_at,
                IdentityRecoveryProofLinkRow.covered_operation_id,
            )
            .limit(limit)
        )
        return tuple(OperationId(value) for value in rows)

    @override
    async def is_linked(self, source: OperationId, target: OperationId) -> bool:
        await self._require_scope()
        return bool(
            await self._session.scalar(
                select(
                    exists().where(
                        IdentityRecoveryProofLinkRow.installation_id == self._installation_id.value,
                        IdentityRecoveryProofLinkRow.authority == self._authority.value,
                        IdentityRecoveryProofLinkRow.covering_operation_id == source.value,
                        IdentityRecoveryProofLinkRow.covered_operation_id == target.value,
                    )
                )
            )
        )

    @staticmethod
    def _admission(row: IdentityRecoveryAdmissionRow) -> IdentityRecoveryAdmissionDTO:
        return IdentityRecoveryAdmissionDTO(
            IdentityRecoveryEventDTO(
                IdentityRecoveryFlowId(row.flow_id),
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(row.authority), IdentitySubject(row.subject)
                ),
                row.event_kind,
            ),
            OperationId(row.operation_id),
        )
