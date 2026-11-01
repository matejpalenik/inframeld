from datetime import datetime
from typing import override

from sqlalchemy import and_, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.repair_project_metadata_authority_command import (
    RepairProjectMetadataAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_facts_dto import (
    ProjectMetadataRepairFactsDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_receipt_dto import (
    ProjectMetadataRepairReceiptDTO,
)
from inframeld_backend.access.application.dtos.project_metadata_repair_result_dto import (
    ProjectMetadataRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.project_metadata_maintenance_error_code import (
    ProjectMetadataMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.project_metadata_maintenance_error import (
    ProjectMetadataMaintenanceError,
)
from inframeld_backend.access.application.protocols.project_metadata_repair_facts_reader import (
    ProjectMetadataRepairFactsReader,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_action_facts_reader import (
    PostgresProjectActionFactsReader,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.host_maintenance_receipt_row import (
    HostMaintenanceReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_metadata_repair_receipt_row import (
    ProjectMetadataRepairReceiptRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresProjectMetadataRepairFactsReader(ProjectMetadataRepairFactsReader):
    """Observe current repair facts after identity, Organization and Project coordination."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Repair facts require an active caller transaction.")

    @override
    async def read(
        self, *, access: AccessContextDTO, command: RepairProjectMetadataAuthorityCommand
    ) -> ProjectMetadataRepairFactsDTO | None:
        self._require_transaction()
        binding = access.authentication_evidence
        if not isinstance(binding, HumanOAuthCredentialBindingDTO):
            raise ProjectMetadataMaintenanceError(Code.INVALID_IDENTITY_PROOF)
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise ProjectMetadataMaintenanceError(Code.DEPENDENCY_UNAVAILABLE)
        if installed != command.expected_installation_id.value:
            raise ProjectMetadataMaintenanceError(Code.INSTALLATION_MISMATCH)

        await PostgresIdentityCoordinator(self._session).acquire(
            installation_id=InstallationId(installed), identity=binding.identity
        )
        organization = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if organization is None:
            return None
        locked_organization = await self._session.scalar(
            select(OrganizationRow.id).where(OrganizationRow.id == organization).with_for_update()
        )
        if locked_organization is None:
            return None
        project = await self._session.scalar(
            select(ProjectRow)
            .where(
                ProjectRow.id == command.project_id.value,
                ProjectRow.organization_id == organization,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if project is None:
            return None

        facts = await PostgresProjectActionFactsReader(self._session).read_action_facts(
            access=access,
            action_id=ActionId("edit-project-metadata"),
            target=ProjectActionTargetDTO(command.project_id),
        )
        if facts is None:
            return None
        if facts.principal.organization_id.value != organization:
            raise RuntimeError("Coordinated repair facts changed their Organization.")
        if facts.principal.kind is not PrincipalKind.HUMAN or facts.oauth_credential_facts is None:
            return None
        grantor = await self._eligible_grantor(command.project_id, InstallationId(installed))
        observed = await self._session.scalar(
            select(func.clock_timestamp(type_=ProjectRow.created_at.type))
        )
        if not isinstance(observed, datetime):
            raise RuntimeError("Repair authorization has no database timestamp.")
        return ProjectMetadataRepairFactsDTO(
            InstallationId(installed),
            facts.principal,
            command.project_id,
            facts.project_status,
            project.access_revision,
            facts.is_project_member,
            facts.has_pending_recovery,
            facts.oauth_credential_facts,
            grantor,
            observed,
        )

    async def _eligible_grantor(
        self, project_id: ProjectId, installation_id: InstallationId
    ) -> bool | None:
        linked = exists().where(HumanIdentityLinkRow.principal_id == PrincipalRow.id)
        pending = (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                HumanIdentityLinkRow.principal_id == PrincipalRow.id,
                IdentityRecoveryAdmissionRow.installation_id == installation_id.value,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate(PrincipalRow)
        )
        statement = (
            select(linked, pending)
            .select_from(PrincipalRow)
            .join(
                ProjectMembershipRow,
                and_(
                    ProjectMembershipRow.principal_id == PrincipalRow.id,
                    ProjectMembershipRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .join(
                ProjectActionGrantRow,
                and_(
                    ProjectActionGrantRow.project_id == ProjectMembershipRow.project_id,
                    ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                ),
            )
            .where(
                ProjectMembershipRow.project_id == project_id.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status == PrincipalStatus.ACTIVE,
                ProjectActionGrantRow.action == "edit-project-metadata",
                ProjectActionGrantRow.can_grant.is_(True),
            )
        )
        unknown = False
        for has_identity, recovering in (await self._session.execute(statement)).tuples():
            if not has_identity:
                unknown = True
            elif not recovering:
                return True
        return None if unknown else False

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> ProjectMetadataRepairReceiptDTO | None:
        self._require_transaction()
        key = (installation_id.value, operation_id.value)
        parent = await self._session.get(HostMaintenanceReceiptRow, key, populate_existing=True)
        if parent is None:
            return None
        if parent.mode != "repair-stranded-authority":
            raise ProjectMetadataMaintenanceError(Code.KEY_REUSED)
        row = await self._session.get(ProjectMetadataRepairReceiptRow, key, populate_existing=True)
        if (
            row is None
            or parent.outcome != "repaired"
            or any(
                value is not None
                for value in (
                    parent.recovery_operation_id,
                    parent.released,
                    parent.run_id,
                    parent.deadline,
                )
            )
        ):
            raise RuntimeError("The stored repair receipt has no valid typed result.")
        return ProjectMetadataRepairReceiptDTO(
            RequestFingerprint(row.request_fingerprint),
            VerifiedHumanIdentityDTO(
                IdentityAuthority(parent.authority), IdentitySubject(parent.subject)
            ),
            row.expected_identity_id,
            parent.operator_label,
            parent.reason,
            row.before_revision,
            parent.authorized_at,
            ProjectMetadataRepairResultDTO(
                operation_id,
                installation_id,
                OrganizationId(row.organization_id),
                ProjectId(row.project_id),
                PrincipalId(row.recipient_id),
                row.after_revision,
            ),
        )
