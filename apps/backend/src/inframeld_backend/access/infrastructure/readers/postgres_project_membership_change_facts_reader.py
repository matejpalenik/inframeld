from typing import override
from uuid import UUID

from sqlalchemy import (
    BigInteger,
    ColumnElement,
    Nullable,
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
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.browser_session_authentication_dto import (
    BrowserSessionAuthenticationDTO,
)
from inframeld_backend.access.application.dtos.human_credential_facts_dto import (
    HumanCredentialFactsDTO,
)
from inframeld_backend.access.application.dtos.human_oauth_credential_binding_dto import (
    HumanOAuthCredentialBindingDTO,
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
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)
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
from inframeld_backend.access.infrastructure.readers.project_principal_queries import (
    ProjectPrincipalQueries,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
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
        self._locked_state: ProjectMembershipChangeFactsDTO | None = None
        self._locked_transaction: AsyncSessionTransaction | None = None

    @override
    async def lock_and_load_membership_state(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        principal_id: PrincipalId,
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
                self._locked_state = await self._read(access, project_id, principal_id)
                self._locked_transaction = self._session.get_transaction()
                return self._locked_state
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _read(
        self,
        access: AccessContextDTO,
        project_id: ProjectId,
        principal_id: PrincipalId,
    ) -> ProjectMembershipChangeFactsDTO | None:
        """Lock the Project and observe the actor and recipient before the application decides the change."""
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
        actor_member = ProjectPrincipalQueries.membership(PrincipalRow.id, project_id, org)
        recipient_member = ProjectPrincipalQueries.membership(recipient.id, project_id, org)
        authority = (
            exists()
            .where(
                ProjectActionGrantRow.project_id == project_id.value,
                ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                ProjectActionGrantRow.action == ProjectAction.MANAGE_PROJECT_MEMBERS.value,
            )
            .correlate(PrincipalRow)
        )
        evidence = access.authentication_evidence
        linked = (
            HumanCredentialStateQueries.binding_matches_actor(evidence)
            if isinstance(
                evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
            )
            else literal(False)
        )
        version = (
            Nullable(HumanCredentialStateQueries.version_for_actor(evidence))
            if isinstance(
                evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
            )
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
                        ProjectPrincipalQueries.pending(PrincipalRow.id, installation),
                        ProjectPrincipalQueries.pending(recipient.id, installation),
                        ProjectPrincipalQueries.coherent_identity(recipient.id, org, installation),
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
        return ProjectMembershipChangeFactsDTO(
            installation_id=installation,
            organization_id=org,
            project_id=ProjectId(project_row.id),
            access_revision=project_row.access_revision,
            action=ProjectActionFactsDTO(
                principal=self._principal(actor_row),
                has_pending_recovery=actor_pending,
                oauth_credential_facts=HumanCredentialFactsDTO(
                    binding_matches,
                    HumanCredentialVersion(current_version)
                    if current_version is not None
                    else None,
                )
                if isinstance(
                    evidence, HumanOAuthCredentialBindingDTO | BrowserSessionAuthenticationDTO
                )
                else None,
                project_status=project_row.status,
                is_project_member=actor_is_member,
                has_exact_action_grant=has_authority,
            ),
            recipient=self._principal(recipient_row) if recipient_row is not None else None,
            recipient_has_pending_recovery=recipient_pending,
            recipient_has_coherent_identity=coherent,
            recipient_is_project_member=recipient_is_member,
        )

    @override
    async def load_departure_responsibilities(
        self, *, facts: ProjectMembershipChangeFactsDTO, principal_id: PrincipalId
    ) -> tuple[ProjectDepartureResponsibilityDTO, ...]:
        if (
            not self._session.in_transaction()
            or not self._session.is_active
            or self._session.get_transaction() is not self._locked_transaction
            or facts is not self._locked_state
            or facts.recipient is None
            or facts.recipient.id != principal_id
            or not facts.recipient_is_project_member
        ):
            raise RuntimeError("Departure observation requires the checked coordinated state.")

        try:
            with self._session.no_autoflush:
                return await self._responsibilities(facts, principal_id)
        except (OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _responsibilities(
        self, facts: ProjectMembershipChangeFactsDTO, departing: PrincipalId
    ) -> tuple[ProjectDepartureResponsibilityDTO, ...]:
        """Observe affected assignments and possible replacements without deciding whether departure is safe."""
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
                    ProjectDepartureTargetKind.PROJECT,
                    project,
                    ActionId(action),
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
                    ProjectDepartureTargetKind.ACCESS_GROUP,
                    group,
                    ActionId(action),
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
                    ProjectDepartureTargetKind.APPLICATION_ACCOUNT,
                    application,
                    ActionId(action),
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
                    ProjectDepartureTargetKind.ACCESS_GROUP,
                    group,
                    None,
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
        """Observe remaining humans and their exact grant or group-manager relationships."""
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
                        ProjectPrincipalQueries.pending(PrincipalRow.id, facts.installation_id),
                        ProjectPrincipalQueries.membership(
                            PrincipalRow.id, facts.project_id, facts.organization_id
                        ),
                        ProjectPrincipalQueries.coherent_identity(
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
                principal=self._principal(principal),
                has_pending_recovery=pending,
                is_project_member=member,
                has_coherent_identity=coherent,
                can_grant=can_grant,
                is_group_member=member_of_group,
                is_group_manager=manages_group,
            )
            for principal, pending, member, coherent, can_grant, member_of_group, manages_group in rows
        )

    @staticmethod
    def _principal(row: PrincipalRow) -> Principal:
        return Principal(
            PrincipalId(row.id), OrganizationId(row.organization_id), row.kind, row.status
        )
