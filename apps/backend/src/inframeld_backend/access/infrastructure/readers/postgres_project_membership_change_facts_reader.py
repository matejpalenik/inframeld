from dataclasses import replace
from typing import override
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Nullable,
    SQLColumnExpression,
    String,
    and_,
    exists,
    func,
    literal,
    or_,
    select,
)
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased
from sqlalchemy.sql.selectable import Exists

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_facts_dto import (
    HumanOAuthCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_departure_candidate_dto import (
    ProjectDepartureCandidateDTO,
)
from inframeld_backend.access.application.dtos.project_departure_responsibility_dto import (
    ProjectDepartureResponsibilityDTO,
)
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.protocols.project_membership_change_facts_reader import (
    ProjectMembershipChangeFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.human_credential_version import (
    HumanCredentialVersion,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.human_credential_version_row import (
    HumanCredentialVersionRow,
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
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresProjectMembershipChangeFactsReader(ProjectMembershipChangeFactsReader):
    """Take the Access turn before observing current authority and affected relationships."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        principal_id: PrincipalId,
        removing: bool,
    ) -> ProjectMembershipChangeFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Membership observation requires the active caller transaction.")
        try:
            with self._session.no_autoflush:
                isolation = await self._session.scalar(
                    select(func.current_setting("transaction_isolation", type_=String()))
                )
                if isolation != "read committed":
                    raise RuntimeError("Membership coordination requires READ COMMITTED isolation.")
                return await self._read(access, project_id, principal_id, removing)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _read(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        principal_id: PrincipalId,
        removing: bool,
    ) -> ProjectMembershipChangeFactsDTO | None:
        organization = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if organization is None:
            return None
        locked_org = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == organization)
            .with_for_update(read=True)
        )
        if locked_org is None:
            return None
        locked_project = await self._session.scalar(
            select(ProjectRow.id)
            .where(ProjectRow.id == project_id.value, ProjectRow.organization_id == locked_org)
            .with_for_update()
        )
        if locked_project is None:
            return None
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise DependencyUnavailableError("The installation identity is not available.")
        installation = InstallationId(installed)
        org = OrganizationId(locked_org)
        recipient = aliased(PrincipalRow, name="membership_recipient")
        actor_member = self._membership(PrincipalRow.id, project_id, org)
        recipient_member = self._membership(recipient.id, project_id, org)
        authority = (
            exists()
            .where(
                ProjectActionGrantRow.project_id == project_id.value,
                ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                ProjectActionGrantRow.action == "manage-project-members",
            )
            .correlate(PrincipalRow)
        )
        evidence = access.authentication_evidence
        linked = (
            HumanCredentialStateQueries.binding_matches_actor(evidence)
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else literal(False)
        )
        version = (
            Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
            if isinstance(evidence, HumanOAuthCredentialBindingDTO)
            else Nullable(literal(None, BigInteger))
        )
        row = (
            (
                await self._session.execute(
                    select(
                        PrincipalRow,
                        ProjectRow,
                        Nullable(recipient),
                        actor_member,
                        recipient_member,
                        authority,
                        self._pending(PrincipalRow.id, installation),
                        self._pending(recipient.id, installation),
                        self._coherent_identity(recipient.id, org, installation),
                        linked,
                        version,
                    )
                    .select_from(PrincipalRow)
                    .join(
                        ProjectRow,
                        and_(
                            ProjectRow.id == locked_project,
                            ProjectRow.organization_id == PrincipalRow.organization_id,
                        ),
                    )
                    .outerjoin(
                        recipient,
                        and_(
                            recipient.id == principal_id.value,
                            recipient.organization_id == locked_org,
                        ),
                    )
                    .where(
                        PrincipalRow.id == access.actor_principal_id.value,
                        PrincipalRow.organization_id == locked_org,
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
            )
            .tuples()
            .one_or_none()
        )
        if row is None:
            return None
        (
            actor_row,
            project_row,
            recipient_row,
            actor_is_member,
            recipient_is_member,
            has_authority,
            actor_pending,
            recipient_pending,
            coherent,
            binding_matches,
            current_version,
        ) = row
        facts = ProjectMembershipChangeFactsDTO(
            installation,
            org,
            ProjectId(project_row.id),
            project_row.access_revision,
            ProjectActionFactsDTO(
                self._principal(actor_row),
                actor_pending,
                HumanOAuthCredentialFactsDTO(
                    binding_matches,
                    HumanCredentialVersion(current_version)
                    if current_version is not None
                    else None,
                )
                if isinstance(evidence, HumanOAuthCredentialBindingDTO)
                else None,
                project_row.status,
                actor_is_member,
                has_authority,
            ),
            self._principal(recipient_row) if recipient_row is not None else None,
            recipient_pending,
            coherent,
            recipient_is_member,
        )
        if removing and recipient_is_member:
            return replace(
                facts, responsibilities=await self._responsibilities(facts, principal_id)
            )
        return facts

    async def _responsibilities(
        self, facts: ProjectMembershipChangeFactsDTO, departing: PrincipalId
    ) -> tuple[ProjectDepartureResponsibilityDTO, ...]:
        project = facts.project_id.value
        result: list[ProjectDepartureResponsibilityDTO] = []
        project_actions = (
            await self._session.scalars(
                select(ProjectActionGrantRow.action).where(
                    ProjectActionGrantRow.project_id == project,
                    ProjectActionGrantRow.recipient_principal_id == departing.value,
                    ProjectActionGrantRow.can_grant.is_(True),
                )
            )
        ).all()
        for action in project_actions:
            grant = (
                exists()
                .where(
                    ProjectActionGrantRow.project_id == project,
                    ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                    ProjectActionGrantRow.action == action,
                    ProjectActionGrantRow.can_grant.is_(True),
                )
                .correlate(PrincipalRow)
            )
            result.append(
                ProjectDepartureResponsibilityDTO(
                    "project",
                    project,
                    ActionId(action),
                    False,
                    False,
                    await self._candidates(facts, departing, grant),
                )
            )

        groups = (
            (
                await self._session.execute(
                    select(GroupActionGrantRow.group_id, GroupActionGrantRow.action).where(
                        GroupActionGrantRow.project_id == project,
                        GroupActionGrantRow.recipient_principal_id == departing.value,
                        GroupActionGrantRow.can_grant.is_(True),
                    )
                )
            )
            .tuples()
            .all()
        )
        for group, action in groups:
            grant = (
                exists()
                .where(
                    GroupActionGrantRow.project_id == project,
                    GroupActionGrantRow.group_id == group,
                    GroupActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    GroupActionGrantRow.recipient_kind == PrincipalRow.kind,
                    GroupActionGrantRow.action == action,
                    GroupActionGrantRow.can_grant.is_(True),
                )
                .correlate(PrincipalRow)
            )
            result.append(
                ProjectDepartureResponsibilityDTO(
                    "access_group",
                    group,
                    ActionId(action),
                    False,
                    action in {"add-documents", "update-documents", "delete-documents"},
                    await self._candidates(facts, departing, grant, group),
                )
            )

        applications = (
            (
                await self._session.execute(
                    select(
                        ApplicationActionGrantRow.application_principal_id,
                        ApplicationActionGrantRow.action,
                    ).where(
                        ApplicationActionGrantRow.project_id == project,
                        ApplicationActionGrantRow.recipient_principal_id == departing.value,
                        ApplicationActionGrantRow.can_grant.is_(True),
                    )
                )
            )
            .tuples()
            .all()
        )
        for application, action in applications:
            grant = (
                exists()
                .where(
                    ApplicationActionGrantRow.project_id == project,
                    ApplicationActionGrantRow.application_principal_id == application,
                    ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    ApplicationActionGrantRow.recipient_kind == PrincipalRow.kind,
                    ApplicationActionGrantRow.action == action,
                    ApplicationActionGrantRow.can_grant.is_(True),
                )
                .correlate(PrincipalRow)
            )
            result.append(
                ProjectDepartureResponsibilityDTO(
                    "application_account",
                    application,
                    ActionId(action),
                    False,
                    False,
                    await self._candidates(facts, departing, grant),
                )
            )

        managed = (
            await self._session.scalars(
                select(GroupManagerRow.group_id).where(
                    GroupManagerRow.project_id == project,
                    GroupManagerRow.principal_id == departing.value,
                )
            )
        ).all()
        for group in managed:
            result.append(
                ProjectDepartureResponsibilityDTO(
                    "access_group",
                    group,
                    None,
                    True,
                    False,
                    await self._candidates(facts, departing, literal(False), group),
                )
            )
        return tuple(result)

    async def _candidates(
        self,
        facts: ProjectMembershipChangeFactsDTO,
        departing: PrincipalId,
        grant: ColumnElement[bool],
        group: UUID | None = None,
    ) -> tuple[ProjectDepartureCandidateDTO, ...]:
        group_member = (
            exists()
            .where(
                GroupMembershipRow.project_id == facts.project_id.value,
                GroupMembershipRow.group_id == group,
                GroupMembershipRow.principal_id == PrincipalRow.id,
            )
            .correlate(PrincipalRow)
            if group is not None
            else literal(False)
        )
        manager = (
            exists()
            .where(
                GroupManagerRow.project_id == facts.project_id.value,
                GroupManagerRow.group_id == group,
                GroupManagerRow.principal_id == PrincipalRow.id,
                GroupManagerRow.principal_kind == PrincipalRow.kind,
            )
            .correlate(PrincipalRow)
            if group is not None
            else literal(False)
        )
        rows = (
            (
                await self._session.execute(
                    select(
                        PrincipalRow,
                        self._pending(PrincipalRow.id, facts.installation_id),
                        self._membership(PrincipalRow.id, facts.project_id, facts.organization_id),
                        self._coherent_identity(
                            PrincipalRow.id, facts.organization_id, facts.installation_id
                        ),
                        grant,
                        group_member,
                        manager,
                    )
                    .where(
                        PrincipalRow.organization_id == facts.organization_id.value,
                        PrincipalRow.id != departing.value,
                        or_(grant, manager),
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
            )
            .tuples()
            .all()
        )
        return tuple(
            ProjectDepartureCandidateDTO(
                self._principal(principal),
                pending,
                member,
                coherent,
                can_grant,
                member_of_group,
                manages_group,
            )
            for principal, pending, member, coherent, can_grant, member_of_group, manages_group in rows
        )

    @staticmethod
    def _membership(
        principal: SQLColumnExpression[UUID], project: ProjectId, organization: OrganizationId
    ) -> Exists:
        return (
            exists()
            .where(
                ProjectMembershipRow.project_id == project.value,
                ProjectMembershipRow.organization_id == organization.value,
                ProjectMembershipRow.principal_id == principal,
            )
            .correlate_except(ProjectMembershipRow)
        )

    @staticmethod
    def _pending(principal: SQLColumnExpression[UUID], installation: InstallationId) -> Exists:
        return (
            select(IdentityRecoveryAdmissionRow.operation_id)
            .join(
                HumanIdentityLinkRow,
                and_(
                    HumanIdentityLinkRow.authority == IdentityRecoveryAdmissionRow.authority,
                    HumanIdentityLinkRow.subject == IdentityRecoveryAdmissionRow.subject,
                ),
            )
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation.value,
                HumanIdentityLinkRow.principal_id == principal,
                IdentityRecoveryAdmissionRow.released_at.is_(None),
            )
            .exists()
            .correlate_except(IdentityRecoveryAdmissionRow, HumanIdentityLinkRow)
        )

    @staticmethod
    def _coherent_identity(
        principal: SQLColumnExpression[UUID],
        organization: OrganizationId,
        installation: InstallationId,
    ) -> Exists:
        version = (
            exists()
            .where(
                HumanCredentialVersionRow.installation_id == installation.value,
                HumanCredentialVersionRow.authority == HumanIdentityLinkRow.authority,
                HumanCredentialVersionRow.subject == HumanIdentityLinkRow.subject,
            )
            .correlate(HumanIdentityLinkRow)
        )
        history = (
            exists()
            .where(
                IdentityRecoveryAdmissionRow.installation_id == installation.value,
                IdentityRecoveryAdmissionRow.authority == HumanIdentityLinkRow.authority,
                IdentityRecoveryAdmissionRow.subject == HumanIdentityLinkRow.subject,
            )
            .correlate(HumanIdentityLinkRow)
        )
        return (
            exists()
            .where(
                HumanIdentityLinkRow.principal_id == principal,
                HumanIdentityLinkRow.organization_id == organization.value,
                HumanIdentityLinkRow.principal_kind == PrincipalKind.HUMAN,
                or_(version, ~history),
            )
            .correlate_except(HumanIdentityLinkRow)
        )

    @staticmethod
    def _principal(row: PrincipalRow) -> Principal:
        return Principal(
            PrincipalId(row.id), OrganizationId(row.organization_id), row.kind, row.status
        )
