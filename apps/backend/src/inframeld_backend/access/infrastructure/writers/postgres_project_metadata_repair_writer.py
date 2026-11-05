from typing import override

from sqlalchemy import func, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.project_metadata_authority_repaired_audit_event_dto import (
    ProjectMetadataAuthorityRepairedAuditEventDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_facts_dto import (
    ProjectMetadataRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_receipt_dto import (
    ProjectMetadataRepairReceiptDTO,
)
from inframeld_backend.access.application.enums.project_metadata_maintenance_error_code import (
    ProjectMetadataMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.project_metadata_maintenance_error import (
    ProjectMetadataMaintenanceError,
)
from inframeld_backend.access.application.protocols.project_metadata_audit_writer import (
    ProjectMetadataAuditWriter,
)
from inframeld_backend.access.application.protocols.project_metadata_repair_writer import (
    ProjectMetadataRepairWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
    ProjectMetadataRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow


class PostgresProjectMetadataRepairWriter(ProjectMetadataRepairWriter):
    """Save one typed operator receipt and its exact assignment in the caller transaction."""

    def __init__(
        self, session: AsyncSession, metadata_audit_writer: ProjectMetadataAuditWriter
    ) -> None:
        self._session = session
        self._metadata_audit_writer = metadata_audit_writer
        self._recorded: ProjectMetadataRepairReceiptDTO | None = None

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Repair persistence requires an active caller transaction.")

    @override
    async def record(self, receipt: ProjectMetadataRepairReceiptDTO) -> bool:
        self._require_transaction()
        result = receipt.result
        if result.access_revision != receipt.before_revision + 1:
            raise RuntimeError("Repair receipt revisions are inconsistent.")
        inserted = await self._session.scalar(
            insert(HostMaintenanceReceiptRow)
            .values(
                installation_id=result.installation_id.value,
                operator_request_id=result.operation_id.value,
                authority=receipt.identity.authority.value,
                subject=receipt.identity.subject.value,
                mode="repair-stranded-authority",
                recovery_operation_id=None,
                operator_label=receipt.operator_label,
                reason=receipt.reason,
                authorized_at=receipt.authorized_at,
                outcome="repaired",
                released=None,
                run_id=None,
                deadline=None,
            )
            .on_conflict_do_nothing(
                index_elements=[
                    HostMaintenanceReceiptRow.installation_id,
                    HostMaintenanceReceiptRow.operator_request_id,
                ]
            )
            .returning(HostMaintenanceReceiptRow.operator_request_id)
        )
        if inserted is None:
            return False
        self._session.add(
            ProjectMetadataRepairReceiptRow(
                installation_id=result.installation_id.value,
                operator_request_id=result.operation_id.value,
                organization_id=result.organization_id.value,
                project_id=result.project_id.value,
                recipient_id=result.recipient_id.value,
                expected_identity_id=receipt.expected_identity_id,
                request_fingerprint=receipt.fingerprint.value,
                before_revision=receipt.before_revision,
                after_revision=result.access_revision,
            )
        )
        await self._session.flush()
        self._recorded = receipt
        return True

    @override
    async def assign(
        self, *, facts: ProjectMetadataRepairFactsDTO, receipt: ProjectMetadataRepairReceiptDTO
    ) -> None:
        self._require_transaction()
        result = receipt.result
        if self._recorded != receipt or (
            facts.installation_id,
            facts.recipient.organization_id,
            facts.project_id,
            facts.recipient.id,
            facts.access_revision,
        ) != (
            result.installation_id,
            result.organization_id,
            result.project_id,
            result.recipient_id,
            receipt.before_revision,
        ):
            raise RuntimeError("Repair assignment does not match its recorded authorization.")
        changed = await self._session.scalar(
            update(ProjectRow)
            .where(
                ProjectRow.id == result.project_id.value,
                ProjectRow.organization_id == result.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
                ProjectRow.access_revision == receipt.before_revision,
            )
            .values(access_revision=result.access_revision)
            .returning(ProjectRow.id)
        )
        if changed is None:
            raise ProjectMetadataMaintenanceError(Code.STALE_REVISION)
        await self._session.execute(
            insert(ProjectActionGrantRow)
            .values(
                project_id=result.project_id.value,
                recipient_principal_id=result.recipient_id.value,
                recipient_kind=PrincipalKind.HUMAN,
                action=ProjectAction.EDIT_PROJECT_METADATA.value,
                can_grant=True,
                assigned_by_principal_id=None,
            )
            .on_conflict_do_update(
                index_elements=[
                    ProjectActionGrantRow.project_id,
                    ProjectActionGrantRow.recipient_principal_id,
                    ProjectActionGrantRow.action,
                ],
                set_={
                    "can_grant": True,
                    "assigned_at": func.clock_timestamp(),
                    "assigned_by_principal_id": None,
                },
            )
        )
        await self._metadata_audit_writer.repaired(
            ProjectMetadataAuthorityRepairedAuditEventDTO(
                organization_id=result.organization_id,
                project_id=result.project_id,
                recipient_id=result.recipient_id,
                operation_id=result.operation_id,
                operator_label=receipt.operator_label,
                reason=receipt.reason,
                before_revision=receipt.before_revision,
                after_revision=result.access_revision,
            )
        )
        self._recorded = None
