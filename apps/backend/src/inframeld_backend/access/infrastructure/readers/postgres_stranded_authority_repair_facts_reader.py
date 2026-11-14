from datetime import datetime
from typing import override

from sqlalchemy import ColumnElement, Nullable, String, and_, exists, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.repair_stranded_authority_command import (
    RepairStrandedAuthorityCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.action_grantor_repair_responsibility_dto import (
    ActionGrantorRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.group_manager_repair_responsibility_dto import (
    GroupManagerRepairResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
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
from inframeld_backend.access.application.dtos.stranded_authority_repair_result_dto import (
    StrandedAuthorityRepairResultDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.enums.repair_responsibility_kind import (
    RepairResponsibilityKind,
)
from inframeld_backend.access.application.enums.stranded_authority_maintenance_error_code import (
    StrandedAuthorityMaintenanceErrorCode as Code,
)
from inframeld_backend.access.application.errors.stranded_authority_maintenance_error import (
    StrandedAuthorityMaintenanceError,
)
from inframeld_backend.access.application.protocols.stranded_authority_repair_facts_reader import (
    StrandedAuthorityRepairFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.readers.project_principal_queries import (
    ProjectPrincipalQueries,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
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
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
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
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.application.value_objects.request_fingerprint import (
    RequestFingerprint,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresStrandedAuthorityRepairFactsReader(StrandedAuthorityRepairFactsReader):
    """Observe one current responsibility under caller-owned identity/Organization/Project turns."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Repair facts require an active caller transaction.")

    @override
    async def read(
        self, *, access: AccessContextDTO, command: RepairStrandedAuthorityCommand
    ) -> StrandedAuthorityRepairFactsDTO | None:
        self._require_transaction()
        binding = access.authentication_evidence
        if not isinstance(binding, HumanOAuthCredentialBindingDTO):
            raise StrandedAuthorityMaintenanceError(Code.INVALID_IDENTITY_PROOF)
        with self._session.no_autoflush:
            installed = await self._session.scalar(
                select(InstallationIdentityRow.installation_id).where(
                    InstallationIdentityRow.singleton_key == 1
                )
            )
            if installed is None:
                raise StrandedAuthorityMaintenanceError(Code.DEPENDENCY_UNAVAILABLE)
            if (
                installed != command.expected_installation_id.value
                or binding.installation_id.value != installed
            ):
                raise StrandedAuthorityMaintenanceError(Code.INSTALLATION_MISMATCH)
            installation = InstallationId(installed)
            await PostgresIdentityCoordinator(self._session).acquire(
                installation_id=installation, identity=binding.identity
            )
            organization = await self._session.scalar(
                select(PrincipalRow.organization_id).where(
                    PrincipalRow.id == access.actor_principal_id.value
                )
            )
            if organization is None:
                return None
            responsibility = command.responsibility
            project_id: ProjectId | None
            if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
                project_id = responsibility.project_id
            else:
                target = responsibility.target
                if isinstance(target, OrganizationGrantTargetDTO):
                    if target.organization_id.value != organization:
                        return None
                    project_id = None
                else:
                    project_id = target.project_id
            locked = await self._session.scalar(
                select(OrganizationRow.id)
                .where(OrganizationRow.id == organization)
                .with_for_update()
            )
            if locked is None:
                return None
            if project_id is None:
                observed = (
                    await self._session.execute(
                        select(
                            PrincipalRow,
                            OrganizationRow.access_revision,
                            HumanCredentialStateQueries.pending_for_principal(
                                PrincipalRow.id, installation
                            ),
                            HumanCredentialStateQueries.binding_matches_actor(binding),
                            Nullable(HumanCredentialStateQueries.version_for_actor(binding)),
                        )
                        .select_from(PrincipalRow)
                        .join(OrganizationRow, OrganizationRow.id == PrincipalRow.organization_id)
                        .where(
                            PrincipalRow.id == access.actor_principal_id.value,
                            OrganizationRow.id == organization,
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                ).one_or_none()
                if observed is None:
                    return None
                actor, revision, recovering, linked, version = observed
                principal = Principal(
                    PrincipalId(actor.id),
                    OrganizationId(actor.organization_id),
                    actor.kind,
                    actor.status,
                )
                member = False
                oauth = HumanCredentialFactsDTO(
                    linked, HumanCredentialVersion(version) if version is not None else None
                )
                status = None
                target_exists, target_accepts_assignment = True, True
            else:
                project = await self._session.scalar(
                    select(ProjectRow)
                    .where(
                        ProjectRow.id == project_id.value,
                        ProjectRow.organization_id == organization,
                    )
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if project is None:
                    return None
                header = (
                    await self._session.execute(ProjectActorQueries.header(access, project_id))
                ).one_or_none()
                if header is None:
                    return None
                (
                    actor,
                    current_project,
                    current_installation,
                    is_member,
                    blocked,
                    linked,
                    version,
                ) = header
                if (
                    current_installation != installed
                    or actor.organization_id != organization
                    or current_project.organization_id != organization
                ):
                    raise RuntimeError(
                        "Coordinated repair observations changed installation or Organization."
                    )
                current = PostgresProjectActorMapper.action(
                    access=access,
                    principal=actor,
                    project=current_project,
                    member=is_member,
                    recovering=blocked,
                    linked=linked,
                    version=version,
                    granted=False,
                )
                if current.oauth_credential_facts is None:
                    return None
                principal = current.principal
                member = current.is_project_member
                recovering = current.has_pending_recovery
                oauth = current.oauth_credential_facts
                status = current.project_status
                revision = project.access_revision
                target_exists, target_accepts_assignment = await self._target_facts(
                    command, OrganizationId(organization)
                )
            if (
                principal.kind is not PrincipalKind.HUMAN
                or principal.organization_id.value != organization
            ):
                return None
            grantor = await self._eligible_holder(
                command, OrganizationId(organization), installation, project_id
            )
            observed_at = await self._session.scalar(
                select(func.clock_timestamp(type_=ProjectRow.created_at.type))
            )
            if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
                raise RuntimeError("Repair authorization requires aware database time.")
            return StrandedAuthorityRepairFactsDTO(
                installation,
                principal,
                responsibility,
                status,
                revision,
                member,
                recovering,
                oauth,
                grantor,
                target_exists,
                target_accepts_assignment,
                observed_at,
            )

    async def _target_facts(
        self, command: RepairStrandedAuthorityCommand, organization: OrganizationId
    ) -> tuple[bool, bool]:
        """Separate a retained target from eligibility for a new assignment."""
        responsibility = command.responsibility
        if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
            project, group = responsibility.project_id, responsibility.access_group_id
        elif isinstance(responsibility.target, AccessGroupGrantTargetDTO):
            project, group = responsibility.target.project_id, responsibility.target.access_group_id
        elif isinstance(responsibility.target, ApplicationAccountGrantTargetDTO):
            target = responsibility.target
            accepts_assignment = await self._session.scalar(
                select(
                    and_(
                        PrincipalRow.status == PrincipalStatus.ACTIVE,
                        ProjectPrincipalQueries.membership(
                            PrincipalRow.id, target.project_id, organization
                        ),
                    )
                )
                .select_from(ApplicationAccountRow)
                .join(
                    PrincipalRow,
                    and_(
                        ApplicationAccountRow.principal_id == PrincipalRow.id,
                        ApplicationAccountRow.organization_id == PrincipalRow.organization_id,
                    ),
                )
                .where(
                    ApplicationAccountRow.project_id == target.project_id.value,
                    ApplicationAccountRow.organization_id == organization.value,
                    ApplicationAccountRow.principal_id == target.application_principal_id.value,
                    ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                    PrincipalRow.kind == PrincipalKind.APPLICATION,
                )
            )
            return accepts_assignment is not None, accepts_assignment is True
        elif isinstance(responsibility.target, ModelConnectionGrantTargetDTO):
            target = responsibility.target
            active = await self._session.scalar(
                select(ModelConnectionRow.retired_at.is_(None)).where(
                    ModelConnectionRow.id == target.model_connection_id.value,
                    ModelConnectionRow.project_id == target.project_id.value,
                    ModelConnectionRow.organization_id == organization.value,
                )
            )
            return active is not None, active is True
        else:
            return True, True
        group_exists = bool(
            await self._session.scalar(
                select(
                    exists().where(
                        AccessGroupRow.project_id == project.value, AccessGroupRow.id == group.value
                    )
                )
            )
        )
        return group_exists, group_exists

    async def _eligible_holder(
        self,
        command: RepairStrandedAuthorityCommand,
        organization: OrganizationId,
        installation: InstallationId,
        project: ProjectId | None,
    ) -> bool | None:
        responsibility = command.responsibility
        manager: ColumnElement[bool] = literal(False)
        group_member: ColumnElement[bool] = literal(False)
        delegated: ColumnElement[bool] = literal(False)
        if isinstance(responsibility, GroupManagerRepairResponsibilityDTO):
            group = responsibility.access_group_id
            manager = (
                exists()
                .where(
                    GroupManagerRow.project_id == responsibility.project_id.value,
                    GroupManagerRow.group_id == group.value,
                    GroupManagerRow.principal_id == PrincipalRow.id,
                )
                .correlate(PrincipalRow)
            )
            group_member = (
                exists()
                .where(
                    GroupMembershipRow.project_id == responsibility.project_id.value,
                    GroupMembershipRow.group_id == group.value,
                    GroupMembershipRow.principal_id == PrincipalRow.id,
                )
                .correlate(PrincipalRow)
            )
        else:
            target, action = responsibility.target, responsibility.action_id.value
            if isinstance(target, OrganizationGrantTargetDTO):
                delegated = (
                    exists()
                    .where(
                        OrganizationActionGrantRow.organization_id == organization.value,
                        OrganizationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                        OrganizationActionGrantRow.recipient_kind == PrincipalKind.HUMAN,
                        OrganizationActionGrantRow.action == action,
                        OrganizationActionGrantRow.can_grant.is_(True),
                    )
                    .correlate(PrincipalRow)
                )
            elif isinstance(target, ProjectGrantTargetDTO):
                delegated = (
                    exists()
                    .where(
                        ProjectActionGrantRow.project_id == target.project_id.value,
                        ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                        ProjectActionGrantRow.recipient_kind == PrincipalKind.HUMAN,
                        ProjectActionGrantRow.action == action,
                        ProjectActionGrantRow.can_grant.is_(True),
                    )
                    .correlate(PrincipalRow)
                )
            elif isinstance(target, AccessGroupGrantTargetDTO):
                delegated = (
                    exists()
                    .where(
                        GroupActionGrantRow.project_id == target.project_id.value,
                        GroupActionGrantRow.group_id == target.access_group_id.value,
                        GroupActionGrantRow.recipient_principal_id == PrincipalRow.id,
                        GroupActionGrantRow.recipient_kind == PrincipalKind.HUMAN,
                        GroupActionGrantRow.action == action,
                        GroupActionGrantRow.can_grant.is_(True),
                    )
                    .correlate(PrincipalRow)
                )
                manager = (
                    exists()
                    .where(
                        GroupManagerRow.project_id == target.project_id.value,
                        GroupManagerRow.group_id == target.access_group_id.value,
                        GroupManagerRow.principal_id == PrincipalRow.id,
                    )
                    .correlate(PrincipalRow)
                )
                group_member = (
                    exists()
                    .where(
                        GroupMembershipRow.project_id == target.project_id.value,
                        GroupMembershipRow.group_id == target.access_group_id.value,
                        GroupMembershipRow.principal_id == PrincipalRow.id,
                    )
                    .correlate(PrincipalRow)
                )
            elif isinstance(target, ModelConnectionGrantTargetDTO):
                grant = ModelConnectionActionGrantRow
                delegated = (
                    exists()
                    .where(
                        grant.project_id == target.project_id.value,
                        grant.model_connection_id == target.model_connection_id.value,
                        grant.recipient_principal_id == PrincipalRow.id,
                        grant.recipient_kind == PrincipalKind.HUMAN,
                        grant.action == action,
                        grant.can_grant.is_(True),
                    )
                    .correlate(PrincipalRow)
                )
            else:
                delegated = (
                    exists()
                    .where(
                        ApplicationActionGrantRow.project_id == target.project_id.value,
                        ApplicationActionGrantRow.application_principal_id
                        == target.application_principal_id.value,
                        ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                        ApplicationActionGrantRow.recipient_kind == PrincipalKind.HUMAN,
                        ApplicationActionGrantRow.action == action,
                        ApplicationActionGrantRow.can_grant.is_(True),
                    )
                    .correlate(PrincipalRow)
                )
        membership = (
            ProjectPrincipalQueries.membership(PrincipalRow.id, project, organization)
            if project is not None
            else literal(True)
        )
        coherent = ProjectPrincipalQueries.coherent_identity(
            PrincipalRow.id, organization, installation
        )
        recovering = ProjectPrincipalQueries.pending(PrincipalRow.id, installation)
        statement = (
            select(coherent, recovering, membership, delegated, group_member, manager)
            .select_from(PrincipalRow)
            .where(
                PrincipalRow.organization_id == organization.value,
                PrincipalRow.kind == PrincipalKind.HUMAN,
                PrincipalRow.status == PrincipalStatus.ACTIVE,
                or_(delegated, manager),
            )
        )
        unknown = False
        for linked, blocked, member, grant, ordinary, manages in (
            await self._session.execute(statement)
        ).tuples():
            if not member or blocked:
                continue
            if not linked or (manages and not ordinary and not grant):
                unknown = True
            elif grant or (ordinary and manages):
                return True
        return None if unknown else False

    @override
    async def receipt(
        self, *, installation_id: InstallationId, operation_id: OperationId
    ) -> StrandedAuthorityRepairReceiptDTO | None:
        self._require_transaction()
        isolation = await self._session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("Repair receipt reads require READ COMMITTED isolation.")
        parent_key = and_(
            HostMaintenanceReceiptRow.installation_id == installation_id.value,
            HostMaintenanceReceiptRow.operator_request_id == operation_id.value,
        )
        original = (
            await self._session.execute(
                select(
                    HostMaintenanceReceiptRow,
                    Nullable(ProjectMetadataRepairReceiptRow),
                    Nullable(StrandedAuthorityRepairReceiptRow),
                )
                .outerjoin(
                    ProjectMetadataRepairReceiptRow,
                    and_(
                        ProjectMetadataRepairReceiptRow.installation_id
                        == HostMaintenanceReceiptRow.installation_id,
                        ProjectMetadataRepairReceiptRow.operator_request_id
                        == HostMaintenanceReceiptRow.operator_request_id,
                    ),
                )
                .outerjoin(
                    StrandedAuthorityRepairReceiptRow,
                    and_(
                        StrandedAuthorityRepairReceiptRow.installation_id
                        == HostMaintenanceReceiptRow.installation_id,
                        StrandedAuthorityRepairReceiptRow.operator_request_id
                        == HostMaintenanceReceiptRow.operator_request_id,
                    ),
                )
                .where(parent_key)
                .execution_options(populate_existing=True, autoflush=False)
            )
        ).one_or_none()
        if original is None:
            return None
        parent, legacy, broader = original
        if parent.mode != "repair-stranded-authority":
            raise StrandedAuthorityMaintenanceError(Code.KEY_REUSED)
        if (
            (legacy is None) == (broader is None)
            or parent.outcome != "repaired"
            or any(
                v is not None
                for v in (
                    parent.recovery_operation_id,
                    parent.released,
                    parent.run_id,
                    parent.deadline,
                )
            )
            or parent.authorized_at.tzinfo is None
        ):
            raise RuntimeError("The stored repair original has no single valid typed result.")
        row = legacy if legacy is not None else broader
        assert row is not None
        try:
            RevisionValidation.require(row.before_revision)
            RevisionValidation.require(row.after_revision)
            if row.after_revision != row.before_revision + 1:
                raise ValueError("Incoherent original revisions.")
            if legacy is not None:
                responsibility = ActionGrantorRepairResponsibilityDTO(
                    ProjectGrantTargetDTO(ProjectId(legacy.project_id)),
                    ActionId(ProjectAction.EDIT_PROJECT_METADATA.value),
                )
            else:
                assert broader is not None
                responsibility = self._decode_responsibility(broader)
            return StrandedAuthorityRepairReceiptDTO(
                RequestFingerprint(row.request_fingerprint),
                VerifiedHumanIdentityDTO(
                    IdentityAuthority(parent.authority), IdentitySubject(parent.subject)
                ),
                row.expected_identity_id,
                parent.operator_label,
                parent.reason,
                row.before_revision,
                parent.authorized_at,
                StrandedAuthorityRepairResultDTO(
                    operation_id,
                    installation_id,
                    OrganizationId(row.organization_id),
                    responsibility,
                    PrincipalId(row.recipient_id),
                    row.after_revision,
                ),
            )
        except (ValueError, TypeError) as error:
            raise RuntimeError("The stored repair original is inconsistent.") from error

    @staticmethod
    def _decode_responsibility(
        row: StrandedAuthorityRepairReceiptRow,
    ) -> GroupManagerRepairResponsibilityDTO | ActionGrantorRepairResponsibilityDTO:
        if (
            row.responsibility_kind == RepairResponsibilityKind.GROUP_MANAGER.value
            and row.target_kind == "access-group"
            and row.project_id is not None
            and row.access_group_id is not None
            and row.model_connection_id is None
            and row.application_account_id is None
            and row.action_id is None
        ):
            return GroupManagerRepairResponsibilityDTO(
                ProjectId(row.project_id), AccessGroupId(row.access_group_id)
            )
        if (
            row.responsibility_kind != RepairResponsibilityKind.ACTION_GRANTOR.value
            or row.action_id is None
        ):
            raise ValueError("Unsupported retained responsibility.")
        action = ActionId(row.action_id)
        if (
            row.target_kind == "organization"
            and row.project_id is None
            and row.access_group_id is None
            and row.model_connection_id is None
            and row.application_account_id is None
        ):
            target = OrganizationGrantTargetDTO(OrganizationId(row.organization_id))
        elif (
            row.target_kind == "project"
            and row.project_id is not None
            and row.access_group_id is None
            and row.model_connection_id is None
            and row.application_account_id is None
            and action.value != ProjectAction.EDIT_PROJECT_METADATA.value
        ):
            target = ProjectGrantTargetDTO(ProjectId(row.project_id))
        elif (
            row.target_kind == "access-group"
            and row.project_id is not None
            and row.access_group_id is not None
            and row.model_connection_id is None
            and row.application_account_id is None
        ):
            target = AccessGroupGrantTargetDTO(
                ProjectId(row.project_id), AccessGroupId(row.access_group_id)
            )
        elif (
            row.target_kind == "application-account"
            and row.project_id is not None
            and row.access_group_id is None
            and row.model_connection_id is None
            and row.application_account_id is not None
        ):
            target = ApplicationAccountGrantTargetDTO(
                ProjectId(row.project_id), PrincipalId(row.application_account_id)
            )
        elif (
            row.target_kind == "model-connection"
            and row.project_id is not None
            and row.access_group_id is None
            and row.application_account_id is None
            and row.model_connection_id is not None
        ):
            target = ModelConnectionGrantTargetDTO(
                ProjectId(row.project_id), ModelConnectionId(row.model_connection_id)
            )
        else:
            raise ValueError("Incoherent retained target scope.")
        return ActionGrantorRepairResponsibilityDTO(target, action)
