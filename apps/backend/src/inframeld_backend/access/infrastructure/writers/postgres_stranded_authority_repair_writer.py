from typing import override
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.stranded_authority_repair_facts_dto import (
    StrandedAuthorityRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repair_receipt_dto import (
    StrandedAuthorityRepairReceiptDTO,
)
from inframeld_backend.access.application.dtos.stranded_authority_repaired_audit_event_dto import (
    StrandedAuthorityRepairedAuditEventDTO,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
    StrandedAuthorityMaintenanceError,
)
from inframeld_backend.access.application.protocols.stranded_authority_audit_writer import (
    StrandedAuthorityAuditWriter,
)
from inframeld_backend.access.application.protocols.stranded_authority_repair_writer import (
    StrandedAuthorityRepairWriter,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_action_grant_row import (
    OrganizationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
    ProjectMetadataRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.access.infrastructure.rows.stranded_authority_repair_receipt_row import (
    StrandedAuthorityRepairReceiptRow,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class PostgresStrandedAuthorityRepairWriter(StrandedAuthorityRepairWriter):
    """Save only the checked exact assignment, original and audit in the caller transaction."""

    def __init__(
        self, session: AsyncSession, repair_audit_writer: StrandedAuthorityAuditWriter
    ) -> None:
        self._session = session
        self._repair_audit_writer = repair_audit_writer
        self._recorded: StrandedAuthorityRepairReceiptDTO | None = None
        self._recorded_transaction: AsyncSessionTransaction | None = None

    def _transaction(self) -> AsyncSessionTransaction:
        transaction = self._session.get_nested_transaction() or self._session.get_transaction()
        if transaction is None or not transaction.is_active or not self._session.is_active:
            raise RuntimeError("Repair persistence requires the active caller transaction.")
        return transaction

    @override
    async def record(self, receipt: StrandedAuthorityRepairReceiptDTO) -> bool:
        transaction = self._transaction()
        result = receipt.result
        RevisionValidation.require(receipt.before_revision)
        RevisionValidation.require(result.access_revision)
        if (
            result.access_revision != receipt.before_revision + 1
            or UUID(receipt.identity.subject.value) != receipt.expected_identity_id
            or receipt.authorized_at.tzinfo is None
        ):
            raise RuntimeError("Repair original changed its verified binding or revision.")
        responsibility = result.responsibility
        if (
            isinstance(responsibility, ActionGrantorRepairResponsibilityDTO)
            and isinstance(responsibility.target, OrganizationGrantTargetDTO)
            and responsibility.target.organization_id != result.organization_id
        ):
            raise RuntimeError("Repair original changed its Organization target.")
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
        if (
            isinstance(responsibility, ActionGrantorRepairResponsibilityDTO)
            and isinstance(responsibility.target, ProjectGrantTargetDTO)
            and responsibility.action_id.value == ProjectAction.EDIT_PROJECT_METADATA.value
        ):
            self._session.add(
                ProjectMetadataRepairReceiptRow(
                    installation_id=result.installation_id.value,
                    operator_request_id=result.operation_id.value,
                    organization_id=result.organization_id.value,
                    project_id=responsibility.target.project_id.value,
                    recipient_id=result.recipient_id.value,
                    expected_identity_id=receipt.expected_identity_id,
                    request_fingerprint=receipt.fingerprint.value,
                    before_revision=receipt.before_revision,
                    after_revision=result.access_revision,
                )
            )
        else:
            self._session.add(self._broader_row(receipt))
        await self._session.flush()
        self._recorded = receipt
        self._recorded_transaction = transaction
        return True

    @staticmethod
    def _broader_row(
        receipt: StrandedAuthorityRepairReceiptDTO,
    ) -> StrandedAuthorityRepairReceiptRow:
        result, responsibility = receipt.result, receipt.result.responsibility
        project: UUID | None = None
        group: UUID | None = None
        application: UUID | None = None
        model_connection: UUID | None = None
        action: str | None = None
        if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
            target_kind = "access-group"
            project, group = responsibility.project_id.value, responsibility.access_group_id.value
        else:
            action = responsibility.action_id.value
            target = responsibility.target
            if isinstance(target, OrganizationGrantTargetDTO):
                target_kind = "organization"
            elif isinstance(target, ProjectGrantTargetDTO):
                target_kind, project = "project", target.project_id.value
            elif isinstance(target, AccessGroupGrantTargetDTO):
                target_kind, project, group = (
                    "access-group",
                    target.project_id.value,
                    target.access_group_id.value,
                )
            elif isinstance(target, ModelConnectionGrantTargetDTO):
                target_kind, project, model_connection = (
                    "model-connection",
                    target.project_id.value,
                    target.model_connection_id.value,
                )
            else:
                target_kind, project, application = (
                    "application-account",
                    target.project_id.value,
                    target.application_principal_id.value,
                )
        return StrandedAuthorityRepairReceiptRow(
            installation_id=result.installation_id.value,
            operator_request_id=result.operation_id.value,
            organization_id=result.organization_id.value,
            recipient_id=result.recipient_id.value,
            expected_identity_id=receipt.expected_identity_id,
            request_fingerprint=receipt.fingerprint.value,
            before_revision=receipt.before_revision,
            after_revision=result.access_revision,
            responsibility_kind=responsibility.kind.value,
            target_kind=target_kind,
            project_id=project,
            access_group_id=group,
            application_account_id=application,
            model_connection_id=model_connection,
            action_id=action,
        )

    @override
    async def assign(
        self, *, facts: StrandedAuthorityRepairFactsDTO, receipt: StrandedAuthorityRepairReceiptDTO
    ) -> None:
        transaction = self._transaction()
        result = receipt.result
        if (
            self._recorded_transaction is not transaction
            or self._recorded != receipt
            or not facts.target_exists
            or facts.eligible_grantor_exists is not False
            or (
                facts.installation_id,
                facts.recipient.organization_id,
                facts.recipient.id,
                facts.responsibility,
                facts.access_revision,
            )
            != (
                result.installation_id,
                result.organization_id,
                result.recipient_id,
                result.responsibility,
                receipt.before_revision,
            )
        ):
            raise RuntimeError("Repair assignment changed its recorded current authorization.")
        recipient = await self._session.scalar(
            select(PrincipalRow.id).where(
                PrincipalRow.id == result.recipient_id.value,
                PrincipalRow.organization_id == result.organization_id.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status == PrincipalStatus.ACTIVE,
            )
        )
        if recipient is None:
            raise RuntimeError("Repair recipient no longer matches the checked active human.")
        responsibility = result.responsibility
        if isinstance(responsibility, ActionGrantorRepairResponsibilityDTO) and isinstance(
            responsibility.target, OrganizationGrantTargetDTO
        ):
            changed = await self._session.scalar(
                update(OrganizationRow)
                .where(
                    OrganizationRow.id == result.organization_id.value,
                    OrganizationRow.access_revision == receipt.before_revision,
                    OrganizationRow.access_revision < RevisionValidation.MAX_VALUE,
                )
                .values(access_revision=result.access_revision)
                .returning(OrganizationRow.id)
            )
        else:
            if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
                project = responsibility.project_id
            else:
                target = responsibility.target
                if isinstance(target, OrganizationGrantTargetDTO):
                    raise RuntimeError("Organization repair has no Project transition.")
                project = target.project_id
            changed = await self._session.scalar(
                update(ProjectRow)
                .where(
                    ProjectRow.id == project.value,
                    ProjectRow.organization_id == result.organization_id.value,
                    ProjectRow.status == ProjectStatus.ACTIVE,
                    ProjectRow.access_revision == receipt.before_revision,
                    ProjectRow.access_revision < RevisionValidation.MAX_VALUE,
                )
                .values(access_revision=result.access_revision)
                .returning(ProjectRow.id)
            )
        if changed is None:
            raise StrandedAuthorityMaintenanceError(Code.STALE_REVISION)
        replacement = {
            "can_grant": True,
            "assigned_by_principal_id": None,
            "assigned_at": func.clock_timestamp(),
        }
        if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
            project, group = responsibility.project_id.value, responsibility.access_group_id.value
            await self._session.execute(
                insert(GroupMembershipRow)
                .values(
                    project_id=project,
                    group_id=group,
                    principal_id=recipient,
                    assigned_by_principal_id=None,
                )
                .on_conflict_do_nothing(
                    index_elements=[
                        GroupMembershipRow.project_id,
                        GroupMembershipRow.group_id,
                        GroupMembershipRow.principal_id,
                    ]
                )
            )
            statement = (
                insert(GroupManagerRow)
                .values(
                    project_id=project,
                    group_id=group,
                    principal_id=recipient,
                    principal_kind=PrincipalKind.HUMAN,
                    assigned_by_principal_id=None,
                )
                .on_conflict_do_update(
                    index_elements=[
                        GroupManagerRow.project_id,
                        GroupManagerRow.group_id,
                        GroupManagerRow.principal_id,
                    ],
                    set_={"assigned_by_principal_id": None, "assigned_at": func.clock_timestamp()},
                )
            )
        else:
            target, action = responsibility.target, responsibility.action_id.value
            if isinstance(target, OrganizationGrantTargetDTO):
                statement = (
                    insert(OrganizationActionGrantRow)
                    .values(
                        organization_id=result.organization_id.value,
                        recipient_principal_id=recipient,
                        recipient_kind=PrincipalKind.HUMAN,
                        action=action,
                        can_grant=True,
                        assigned_by_principal_id=None,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            OrganizationActionGrantRow.organization_id,
                            OrganizationActionGrantRow.recipient_principal_id,
                            OrganizationActionGrantRow.action,
                        ],
                        set_=replacement,
                    )
                )
            elif isinstance(target, ProjectGrantTargetDTO):
                statement = (
                    insert(ProjectActionGrantRow)
                    .values(
                        project_id=target.project_id.value,
                        recipient_principal_id=recipient,
                        recipient_kind=PrincipalKind.HUMAN,
                        action=action,
                        can_grant=True,
                        assigned_by_principal_id=None,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            ProjectActionGrantRow.project_id,
                            ProjectActionGrantRow.recipient_principal_id,
                            ProjectActionGrantRow.action,
                        ],
                        set_=replacement,
                    )
                )
            elif isinstance(target, AccessGroupGrantTargetDTO):
                statement = (
                    insert(GroupActionGrantRow)
                    .values(
                        project_id=target.project_id.value,
                        group_id=target.access_group_id.value,
                        recipient_principal_id=recipient,
                        recipient_kind=PrincipalKind.HUMAN,
                        action=action,
                        can_grant=True,
                        assigned_by_principal_id=None,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            GroupActionGrantRow.project_id,
                            GroupActionGrantRow.group_id,
                            GroupActionGrantRow.recipient_principal_id,
                            GroupActionGrantRow.action,
                        ],
                        set_=replacement,
                    )
                )
            elif isinstance(target, ModelConnectionGrantTargetDTO):
                grant = ModelConnectionActionGrantRow
                statement = (
                    insert(grant)
                    .values(
                        project_id=target.project_id.value,
                        model_connection_id=target.model_connection_id.value,
                        recipient_principal_id=recipient,
                        recipient_kind=PrincipalKind.HUMAN,
                        action=action,
                        can_grant=True,
                        assigned_by_principal_id=None,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            grant.project_id,
                            grant.model_connection_id,
                            grant.recipient_principal_id,
                            grant.action,
                        ],
                        set_=replacement,
                    )
                )
            else:
                statement = (
                    insert(ApplicationActionGrantRow)
                    .values(
                        project_id=target.project_id.value,
                        application_principal_id=target.application_principal_id.value,
                        recipient_principal_id=recipient,
                        recipient_kind=PrincipalKind.HUMAN,
                        action=action,
                        can_grant=True,
                        assigned_by_principal_id=None,
                    )
                    .on_conflict_do_update(
                        index_elements=[
                            ApplicationActionGrantRow.project_id,
                            ApplicationActionGrantRow.application_principal_id,
                            ApplicationActionGrantRow.recipient_principal_id,
                            ApplicationActionGrantRow.action,
                        ],
                        set_=replacement,
                    )
                )
        await self._session.execute(statement)
        await self._repair_audit_writer.repaired(
            StrandedAuthorityRepairedAuditEventDTO(
                result.organization_id,
                result.recipient_id,
                responsibility,
                result.operation_id,
                receipt.operator_label,
                receipt.reason,
                receipt.before_revision,
                result.access_revision,
            )
        )
        await self._session.flush()
