import asyncio
from typing import override
from uuid import UUID

from sqlalchemy import ColumnElement, DateTime, String, exists, func, literal, or_, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_group_change_facts_dto import (
    AccessGroupChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_management_facts_dto import (
    AccessGroupGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_management_facts_dto import (
    ApplicationAccountGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_activation_facts_dto import (
    InvitationActivationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_admission_only_intent_dto import (
    InvitationAdmissionOnlyIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_dto import (
    InvitationAssignmentDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_facts_dto import (
    InvitationAssignmentFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_assignment_state_dto import (
    InvitationAssignmentStateDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_issuer_facts_dto import (
    InvitationIssuerFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.model_connection_grant_facts_dto import (
    ModelConnectionGrantFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_access_facts_dto import (
    OrganizationAccessFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_action_grant_dto import (
    OrganizationActionGrantDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_management_facts_dto import (
    OrganizationGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_grant_management_facts_dto import (
    ProjectActionGrantManagementFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.project_membership_change_facts_dto import (
    ProjectMembershipChangeFactsDTO,
)
from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.invitation_assignment_facts_reader import (
    InvitationAssignmentFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policy_inputs.organization_grant_candidate_policy_input import (
    OrganizationGrantCandidatePolicyInput,
)
from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.action_grant_state import ActionGrantState
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_human_credential_state_mapper import (
    PostgresHumanCredentialStateMapper,
)
from inframeld_backend.access.infrastructure.readers.human_credential_state_queries import (
    HumanCredentialStateQueries,
)
from inframeld_backend.access.infrastructure.readers.model_connection_grant_queries import (
    ModelConnectionGrantQueries,
)
from inframeld_backend.access.infrastructure.readers.postgres_invitation_facts_reader import (
    PostgresInvitationFactsReader,
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
from inframeld_backend.access.infrastructure.rows.human_identity_link_row import (
    HumanIdentityLinkRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_row import InvitationRow
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
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresInvitationAssignmentFactsReader(InvitationAssignmentFactsReader):
    """Observe activation facts without presenting the retained issuer as an authenticated actor."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Activation facts require the active caller transaction.")

    @staticmethod
    def _project_id(intent: InvitationAssignmentDTO) -> ProjectId | None:
        if isinstance(
            intent,
            (
                InvitationProjectMembershipIntentDTO,
                InvitationGroupMembershipIntentDTO,
                InvitationGroupManagerIntentDTO,
            ),
        ):
            return intent.project_id
        if isinstance(intent, InvitationActionGrantIntentDTO) and isinstance(
            intent.target,
            (ProjectGrantTargetDTO, AccessGroupGrantTargetDTO, ApplicationAccountGrantTargetDTO),
        ):
            return intent.target.project_id
        return None

    @override
    async def lock_for_activation(
        self, *, identity: VerifiedHumanIdentityDTO, digest: InvitationTokenDigest
    ) -> InvitationActivationFactsDTO | None:
        self._require_transaction()
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    installed = await self._session.scalar(
                        select(InstallationIdentityRow.installation_id).where(
                            InstallationIdentityRow.singleton_key == 1
                        )
                    )
                    if installed is None:
                        raise DependencyUnavailableError()
                    installation = InstallationId(installed)
                    await PostgresIdentityCoordinator(self._session).acquire(
                        installation_id=installation, identity=identity
                    )
                    reader = PostgresInvitationFactsReader(self._session)
                    invitation = await reader.read_by_digest(digest)
                    if invitation is None:
                        return None
                    organization = await self._session.scalar(
                        select(OrganizationRow.id)
                        .where(OrganizationRow.id == invitation.organization_id.value)
                        .with_for_update()
                    )
                    if organization is None:
                        return None
                    projects = {
                        project
                        for intent in invitation.assignments
                        if (project := self._project_id(intent)) is not None
                    }
                    projects.update(
                        (
                            await reader.model_projects(
                                invitation.organization_id, invitation.assignments
                            )
                        ).values()
                    )
                    for project in sorted(projects, key=lambda item: item.value.int):
                        # Missing or deleted targets do not preempt eligible original lookup.
                        await self._session.scalar(
                            select(ProjectRow.id)
                            .where(
                                ProjectRow.id == project.value,
                                ProjectRow.organization_id == organization,
                            )
                            .with_for_update()
                        )
                    invitation = await reader.read_by_digest(digest)
                    if invitation is None:
                        return None
                    revision = await self._session.scalar(
                        select(OrganizationRow.access_revision).where(
                            OrganizationRow.id == organization
                        )
                    )
                    link = await self._session.scalar(
                        select(HumanIdentityLinkRow)
                        .where(
                            HumanIdentityLinkRow.authority == identity.authority.value,
                            HumanIdentityLinkRow.subject == identity.subject.value,
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                    principal = None
                    if link is not None:
                        row = await self._session.scalar(
                            select(PrincipalRow)
                            .where(
                                PrincipalRow.id == link.principal_id,
                                PrincipalRow.organization_id == link.organization_id,
                                PrincipalRow.kind == link.principal_kind,
                            )
                            .execution_options(populate_existing=True, autoflush=False)
                        )
                        if row is None or link.principal_kind is not PrincipalKind.HUMAN:
                            raise DependencyUnavailableError(
                                "The recipient identity link is incoherent."
                            )
                        principal = Principal(
                            id=PrincipalId(row.id),
                            organization_id=OrganizationId(row.organization_id),
                            kind=row.kind,
                            status=row.status,
                        )
                    state_row = (
                        (
                            await self._session.execute(
                                HumanCredentialStateQueries.for_identity(identity)
                            )
                        )
                        .tuples()
                        .one_or_none()
                    )
                    state = PostgresHumanCredentialStateMapper.to_state(identity, state_row)
                    if (
                        state_row is None
                        or state.installation_id != installation
                        or revision is None
                    ):
                        raise DependencyUnavailableError()
                    memberships: frozenset[ProjectId] = frozenset()
                    if principal is not None:
                        memberships = frozenset(
                            ProjectId(value)
                            for value in (
                                await self._session.scalars(
                                    select(ProjectMembershipRow.project_id)
                                    .join(
                                        ProjectRow, ProjectRow.id == ProjectMembershipRow.project_id
                                    )
                                    .where(
                                        ProjectMembershipRow.organization_id == organization,
                                        ProjectMembershipRow.principal_id == principal.id.value,
                                        ProjectMembershipRow.principal_kind == PrincipalKind.HUMAN,
                                        ProjectRow.organization_id == organization,
                                        ProjectRow.status == ProjectStatus.ACTIVE,
                                    )
                                )
                            ).all()
                        )
                    now = await self._session.scalar(
                        select(func.clock_timestamp(type_=DateTime(timezone=True)))
                    )
                    if now is None:
                        raise DependencyUnavailableError()
                    return InvitationActivationFactsDTO(
                        invitation=invitation,
                        principal=principal,
                        credential_state=state,
                        has_credential_history=state_row[3],
                        current_time=now,
                        organization_access_revision=revision,
                        project_memberships=memberships,
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def read_current_issuer(
        self, *, invitation: InvitationRecordDTO
    ) -> InvitationIssuerFactsDTO | None:
        self._require_transaction()
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    return await self._read_issuer(invitation, invitation.assignments)
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _read_issuer(
        self, invitation: InvitationRecordDTO, intents: tuple[InvitationAssignmentDTO, ...]
    ) -> InvitationIssuerFactsDTO | None:
        """Observe the same current issuer header and only the requested concrete effects."""
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise DependencyUnavailableError()
        installation = InstallationId(installed)
        row = (
            (
                await self._session.execute(
                    select(
                        PrincipalRow,
                        OrganizationRow.access_revision,
                        HumanCredentialStateQueries.coherent_for_principal(
                            PrincipalRow.id, invitation.organization_id, installation
                        ).label("issuer_coherent"),
                        HumanCredentialStateQueries.pending_for_principal(
                            PrincipalRow.id, installation
                        ).label("issuer_recovering"),
                    )
                    .join(
                        OrganizationRow,
                        OrganizationRow.id == PrincipalRow.organization_id,
                    )
                    .where(
                        PrincipalRow.id == invitation.issuer_principal_id.value,
                        PrincipalRow.organization_id == invitation.organization_id.value,
                    )
                    .execution_options(populate_existing=True, autoflush=False)
                )
            )
            .tuples()
            .one_or_none()
        )
        if row is None:
            return None
        principal_row, revision, coherent, recovering = row
        principal = Principal(
            id=PrincipalId(principal_row.id),
            organization_id=OrganizationId(principal_row.organization_id),
            kind=principal_row.kind,
            status=principal_row.status,
        )
        grants = (
            (
                await self._session.execute(
                    select(
                        OrganizationActionGrantRow.action,
                        OrganizationActionGrantRow.can_grant,
                    ).where(
                        OrganizationActionGrantRow.organization_id
                        == invitation.organization_id.value,
                        OrganizationActionGrantRow.recipient_principal_id == principal.id.value,
                        OrganizationActionGrantRow.recipient_kind == principal.kind,
                    )
                )
            )
            .tuples()
            .all()
        )
        model_projects = await PostgresInvitationFactsReader(self._session).model_projects(
            invitation.organization_id, intents
        )
        assignments = tuple(
            [
                await self._assignment(
                    invitation, principal, installation, recovering, intent, model_projects
                )
                for intent in intents
            ]
        )
        return InvitationIssuerFactsDTO(
            organization_access=OrganizationAccessFactsDTO(
                principal=principal,
                access_revision=revision,
                grants=tuple(
                    OrganizationActionGrantDTO(action_id=ActionId(action), can_grant=can_grant)
                    for action, can_grant in grants
                ),
                has_pending_recovery=recovering,
                oauth_credential_facts=None,
            ),
            has_coherent_identity=coherent,
            assignments=assignments,
        )

    async def _assignment(
        self,
        invitation: InvitationRecordDTO,
        principal: Principal,
        installation: InstallationId,
        recovering: bool,
        intent: InvitationAssignmentDTO,
        model_projects: dict[UUID, ProjectId],
    ) -> InvitationAssignmentFactsDTO:
        organization = invitation.organization_id
        project_id = (
            model_projects.get(intent.target.model_connection_id)
            if isinstance(intent, InvitationActionGrantIntentDTO)
            and isinstance(intent.target, InvitationModelConnectionTargetDTO)
            else self._project_id(intent)
        )
        project = None
        target_exists = isinstance(intent, InvitationAdmissionOnlyIntentDTO) or (
            isinstance(intent, InvitationActionGrantIntentDTO)
            and isinstance(intent.target, OrganizationGrantTargetDTO)
            and intent.target.organization_id == organization
        )
        delegated = member = manager = False
        if project_id is not None:
            project_row = await self._session.scalar(
                select(ProjectRow)
                .where(
                    ProjectRow.id == project_id.value,
                    ProjectRow.organization_id == organization.value,
                )
                .execution_options(populate_existing=True, autoflush=False)
            )
            if project_row is not None:
                actor_member = bool(
                    await self._session.scalar(
                        select(
                            exists().where(
                                ProjectMembershipRow.project_id == project_id.value,
                                ProjectMembershipRow.organization_id == organization.value,
                                ProjectMembershipRow.principal_id == principal.id.value,
                                ProjectMembershipRow.principal_kind == principal.kind,
                            )
                        )
                    )
                )
                exact: bool | None = None
                if isinstance(intent, InvitationProjectMembershipIntentDTO) or (
                    isinstance(intent, InvitationActionGrantIntentDTO)
                    and isinstance(intent.target, ProjectGrantTargetDTO)
                ):
                    action = (
                        ProjectAction.MANAGE_PROJECT_MEMBERS.value
                        if isinstance(intent, InvitationProjectMembershipIntentDTO)
                        else intent.action_id.value
                    )
                    exact = await self._session.scalar(
                        select(ProjectActionGrantRow.can_grant).where(
                            ProjectActionGrantRow.project_id == project_id.value,
                            ProjectActionGrantRow.recipient_principal_id == principal.id.value,
                            ProjectActionGrantRow.recipient_kind == principal.kind,
                            ProjectActionGrantRow.action == action,
                        )
                    )
                    delegated, target_exists = exact is True, True
                elif isinstance(
                    intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
                ) or (
                    isinstance(intent, InvitationActionGrantIntentDTO)
                    and isinstance(intent.target, AccessGroupGrantTargetDTO)
                ):
                    if isinstance(intent, InvitationActionGrantIntentDTO):
                        if not isinstance(intent.target, AccessGroupGrantTargetDTO):
                            raise RuntimeError("The checked group intent changed its target.")
                        group = intent.target.access_group_id
                    else:
                        group = intent.access_group_id
                    target_exists = (
                        await self._session.scalar(
                            select(AccessGroupRow.id).where(
                                AccessGroupRow.id == group.value,
                                AccessGroupRow.project_id == project_id.value,
                            )
                        )
                        is not None
                    )
                    member = bool(
                        await self._session.scalar(
                            select(
                                exists().where(
                                    GroupMembershipRow.project_id == project_id.value,
                                    GroupMembershipRow.group_id == group.value,
                                    GroupMembershipRow.principal_id == principal.id.value,
                                )
                            )
                        )
                    )
                    manager = bool(
                        await self._session.scalar(
                            select(
                                exists().where(
                                    GroupManagerRow.project_id == project_id.value,
                                    GroupManagerRow.group_id == group.value,
                                    GroupManagerRow.principal_id == principal.id.value,
                                    GroupManagerRow.principal_kind == PrincipalKind.HUMAN,
                                )
                            )
                        )
                    )
                    if isinstance(intent, InvitationActionGrantIntentDTO):
                        delegated = (
                            await self._session.scalar(
                                select(GroupActionGrantRow.can_grant).where(
                                    GroupActionGrantRow.project_id == project_id.value,
                                    GroupActionGrantRow.group_id == group.value,
                                    GroupActionGrantRow.recipient_principal_id
                                    == principal.id.value,
                                    GroupActionGrantRow.recipient_kind == principal.kind,
                                    GroupActionGrantRow.action == intent.action_id.value,
                                )
                            )
                            is True
                        )
                elif isinstance(intent, InvitationActionGrantIntentDTO) and isinstance(
                    intent.target, ApplicationAccountGrantTargetDTO
                ):
                    application = intent.target.application_principal_id
                    target_exists = (
                        await self._session.scalar(
                            select(ApplicationAccountRow.principal_id)
                            .join(
                                PrincipalRow, PrincipalRow.id == ApplicationAccountRow.principal_id
                            )
                            .where(
                                ApplicationAccountRow.principal_id == application.value,
                                ApplicationAccountRow.project_id == project_id.value,
                                ApplicationAccountRow.organization_id == organization.value,
                                ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                                PrincipalRow.organization_id == organization.value,
                                PrincipalRow.kind == PrincipalKind.APPLICATION,
                                PrincipalRow.status == PrincipalStatus.ACTIVE,
                                exists().where(
                                    ProjectMembershipRow.project_id == project_id.value,
                                    ProjectMembershipRow.organization_id == organization.value,
                                    ProjectMembershipRow.principal_id == application.value,
                                    ProjectMembershipRow.application_principal_id
                                    == application.value,
                                    ProjectMembershipRow.principal_kind
                                    == PrincipalKind.APPLICATION,
                                ),
                            )
                        )
                        is not None
                    )
                    delegated = (
                        await self._session.scalar(
                            select(ApplicationActionGrantRow.can_grant).where(
                                ApplicationActionGrantRow.project_id == project_id.value,
                                ApplicationActionGrantRow.application_principal_id
                                == application.value,
                                ApplicationActionGrantRow.recipient_principal_id
                                == principal.id.value,
                                ApplicationActionGrantRow.recipient_kind == principal.kind,
                                ApplicationActionGrantRow.action == intent.action_id.value,
                            )
                        )
                        is True
                    )
                elif isinstance(intent, InvitationActionGrantIntentDTO) and isinstance(
                    intent.target, InvitationModelConnectionTargetDTO
                ):
                    (
                        target_exists,
                        delegated,
                    ) = await ModelConnectionGrantQueries.invitation_authority(
                        self._session,
                        organization,
                        project_id,
                        intent.target,
                        principal.id,
                        principal.kind,
                        intent.action_id,
                    )
                project = ProjectMembershipObservationDTO(
                    installation_id=installation,
                    organization_id=organization,
                    project_id=project_id,
                    access_revision=project_row.access_revision,
                    action=ProjectActionFactsDTO(
                        principal=principal,
                        has_pending_recovery=recovering,
                        oauth_credential_facts=None,
                        project_status=project_row.status,
                        is_project_member=actor_member,
                        has_exact_action_grant=exact is not None,
                    ),
                )
        return InvitationAssignmentFactsDTO(
            intent=intent,
            project=project,
            target_exists=target_exists,
            actor_can_grant=delegated,
            actor_is_group_member=member,
            actor_is_group_manager=manager,
        )

    @override
    async def read_assignment_states(
        self, *, invitation: InvitationRecordDTO, recipient: Principal | None
    ) -> tuple[InvitationAssignmentStateDTO, ...] | None:
        self._require_transaction()
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    return await self._read_states(invitation, recipient, invitation.assignments)
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    @override
    async def read_assignment_state(
        self, *, invitation_id: InvitationId, recipient: Principal, intent: InvitationAssignmentDTO
    ) -> InvitationAssignmentStateDTO | None:
        self._require_transaction()
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    digest = await self._session.scalar(
                        select(InvitationRow.token_digest).where(
                            InvitationRow.id == invitation_id.value
                        )
                    )
                    if digest is None:
                        return None
                    invitation = await PostgresInvitationFactsReader(self._session).read_by_digest(
                        InvitationTokenDigest(digest)
                    )
                    if invitation is None or intent not in invitation.assignments:
                        return None
                    states = await self._read_states(invitation, recipient, (intent,))
                    return states[0] if states else None
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _read_states(
        self,
        invitation: InvitationRecordDTO,
        recipient: Principal | None,
        intents: tuple[InvitationAssignmentDTO, ...],
    ) -> tuple[InvitationAssignmentStateDTO, ...] | None:
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Assignment observations require READ COMMITTED isolation.")
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id).where(
                InstallationIdentityRow.singleton_key == 1
            )
        )
        if installed is None:
            raise DependencyUnavailableError()
        installation = InstallationId(installed)
        issuer = await self._read_issuer(invitation, intents)
        if issuer is None:
            return None
        current_recipient, pending, coherent = None, False, False
        if recipient is not None:
            row = (
                (
                    await self._session.execute(
                        select(
                            PrincipalRow,
                            HumanCredentialStateQueries.pending_for_principal(
                                PrincipalRow.id, installation
                            ),
                            HumanCredentialStateQueries.coherent_for_principal(
                                PrincipalRow.id, invitation.organization_id, installation
                            ),
                        )
                        .where(
                            PrincipalRow.id == recipient.id.value,
                            PrincipalRow.organization_id == invitation.organization_id.value,
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                )
                .tuples()
                .one_or_none()
            )
            if row is None:
                return None
            current_recipient = self._principal(row[0])
            pending, coherent = row[1], row[2]
        states: list[InvitationAssignmentStateDTO] = []
        for intent, observed in zip(intents, issuer.assignments, strict=True):
            if observed.intent != intent or not observed.target_exists:
                return None
            if isinstance(intent, InvitationAdmissionOnlyIntentDTO):
                continue
            state = await self._native_state(
                invitation, issuer, observed, installation, current_recipient, pending, coherent
            )
            if state is None:
                return None
            states.append(state)
        return tuple(states)

    async def _native_state(
        self,
        invitation: InvitationRecordDTO,
        issuer: InvitationIssuerFactsDTO,
        observed: InvitationAssignmentFactsDTO,
        installation: InstallationId,
        recipient: Principal | None,
        pending: bool,
        coherent: bool,
    ) -> InvitationAssignmentStateDTO | None:
        intent, organization = observed.intent, invitation.organization_id
        project = observed.project
        member = False
        if project is not None and recipient is not None:
            member = bool(
                await self._session.scalar(
                    select(
                        exists().where(
                            ProjectMembershipRow.project_id == project.project_id.value,
                            ProjectMembershipRow.organization_id == organization.value,
                            ProjectMembershipRow.principal_id == recipient.id.value,
                            ProjectMembershipRow.principal_kind == recipient.kind,
                        )
                    )
                )
            )
        if isinstance(intent, InvitationProjectMembershipIntentDTO):
            if project is None:
                return None
            return InvitationAssignmentStateDTO(
                intent=intent,
                facts=ProjectMembershipChangeFactsDTO(
                    installation_id=installation,
                    organization_id=organization,
                    project_id=project.project_id,
                    access_revision=project.access_revision,
                    action=project.action,
                    recipient=recipient,
                    recipient_has_pending_recovery=pending,
                    recipient_has_coherent_identity=coherent,
                    recipient_is_project_member=member,
                ),
            )
        if isinstance(
            intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
        ):
            if project is None:
                return None
            ordinary = manager = False
            if recipient is not None:
                ordinary = bool(
                    await self._session.scalar(
                        select(
                            exists().where(
                                GroupMembershipRow.project_id == intent.project_id.value,
                                GroupMembershipRow.group_id == intent.access_group_id.value,
                                GroupMembershipRow.principal_id == recipient.id.value,
                            )
                        )
                    )
                )
                manager = bool(
                    await self._session.scalar(
                        select(
                            exists().where(
                                GroupManagerRow.project_id == intent.project_id.value,
                                GroupManagerRow.group_id == intent.access_group_id.value,
                                GroupManagerRow.principal_id == recipient.id.value,
                                GroupManagerRow.principal_kind == recipient.kind,
                            )
                        )
                    )
                )
            return InvitationAssignmentStateDTO(
                intent=intent,
                facts=AccessGroupChangeFactsDTO(
                    organization_id=organization,
                    project_id=project.project_id,
                    access_revision=project.access_revision,
                    group_id=intent.access_group_id,
                    action=project.action,
                    recipient=recipient,
                    recipient_is_project_member=member,
                    recipient_has_pending_recovery=pending,
                    recipient_has_coherent_identity=coherent,
                    relationships=AccessGroupRelationships(member=ordinary, manager=manager),
                ),
            )
        if not isinstance(intent, InvitationActionGrantIntentDTO):
            return None
        target = intent.target
        if isinstance(target, OrganizationGrantTargetDTO):
            before = (
                await self._session.scalar(
                    select(OrganizationActionGrantRow.can_grant).where(
                        OrganizationActionGrantRow.organization_id == organization.value,
                        OrganizationActionGrantRow.recipient_principal_id == recipient.id.value,
                        OrganizationActionGrantRow.recipient_kind == recipient.kind,
                        OrganizationActionGrantRow.action == intent.action_id.value,
                    )
                )
                if recipient is not None
                else None
            )
            candidates = (
                (
                    await self._session.execute(
                        select(
                            PrincipalRow,
                            HumanCredentialStateQueries.pending_for_principal(
                                PrincipalRow.id, installation
                            ),
                            HumanCredentialStateQueries.coherent_for_principal(
                                PrincipalRow.id, organization, installation
                            ),
                        )
                        .where(
                            PrincipalRow.organization_id == organization.value,
                            self._grant_expression(intent),
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                )
                .tuples()
                .all()
            )
            return InvitationAssignmentStateDTO(
                intent=intent,
                facts=OrganizationGrantManagementFactsDTO(
                    installation_id=installation,
                    organization_id=organization,
                    action_id=intent.action_id,
                    access_revision=issuer.organization_access.access_revision,
                    actor=issuer.organization_access.principal,
                    actor_can_grant=any(
                        g.action_id == intent.action_id and g.can_grant
                        for g in issuer.organization_access.grants
                    ),
                    actor_has_pending_recovery=issuer.organization_access.has_pending_recovery,
                    actor_oauth_credential_facts=None,
                    recipient=recipient,
                    recipient_has_pending_recovery=pending,
                    recipient_has_coherent_identity=coherent,
                    assignment=ActionGrantState(can_grant=before),
                    other_grantors=tuple(
                        OrganizationGrantCandidatePolicyInput(
                            principal=self._principal(row),
                            has_pending_recovery=blocked,
                            has_coherent_identity=linked,
                            can_grant=True,
                        )
                        for row, blocked, linked in candidates
                        if recipient is None or row.id != recipient.id.value
                    ),
                ),
            )
        if project is None:
            return None
        grantors = await self._grantors(intent, organization, project.project_id, installation)
        if isinstance(target, ProjectGrantTargetDTO):
            return InvitationAssignmentStateDTO(
                intent=intent,
                facts=ProjectActionGrantManagementFactsDTO(
                    installation_id=installation,
                    organization_id=organization,
                    project_id=project.project_id,
                    action_id=intent.action_id,
                    grant=ProjectGrantChangeFactsDTO(
                        actor=project.action.principal,
                        has_pending_recovery=project.action.has_pending_recovery,
                        oauth_credential_facts=None,
                        recipient=recipient,
                        project_status=project.action.project_status,
                        project_access_revision=project.access_revision,
                        actor_is_project_member=project.action.is_project_member,
                        recipient_is_project_member=member,
                        actor_can_grant_action=observed.actor_can_grant,
                    ),
                    recipient_has_pending_recovery=pending,
                    recipient_has_coherent_identity=coherent,
                    recipient_application_is_project_bound=False,
                    other_grantors=grantors,
                ),
            )
        if isinstance(target, AccessGroupGrantTargetDTO):
            before = (
                await self._session.scalar(
                    select(GroupActionGrantRow.can_grant).where(
                        GroupActionGrantRow.project_id == project.project_id.value,
                        GroupActionGrantRow.group_id == target.access_group_id.value,
                        GroupActionGrantRow.recipient_principal_id == recipient.id.value,
                        GroupActionGrantRow.recipient_kind == recipient.kind,
                        GroupActionGrantRow.action == intent.action_id.value,
                    )
                )
                if recipient is not None
                else None
            )
            return InvitationAssignmentStateDTO(
                intent=intent,
                facts=AccessGroupGrantManagementFactsDTO(
                    installation_id=installation,
                    organization_id=organization,
                    project_id=project.project_id,
                    group_id=target.access_group_id,
                    action_id=intent.action_id,
                    access_revision=project.access_revision,
                    actor=project.action,
                    actor_can_grant=observed.actor_can_grant,
                    actor_is_group_member=observed.actor_is_group_member,
                    actor_is_group_manager=observed.actor_is_group_manager,
                    recipient=recipient,
                    recipient_is_project_member=member,
                    recipient_has_pending_recovery=pending,
                    recipient_has_coherent_identity=coherent,
                    recipient_application_is_bound=False,
                    assignment=ActionGrantState(can_grant=before),
                    grantors=grantors,
                ),
            )
        if isinstance(target, ApplicationAccountGrantTargetDTO):
            before = (
                await self._session.scalar(
                    select(ApplicationActionGrantRow.can_grant).where(
                        ApplicationActionGrantRow.project_id == project.project_id.value,
                        ApplicationActionGrantRow.application_principal_id
                        == target.application_principal_id.value,
                        ApplicationActionGrantRow.recipient_principal_id == recipient.id.value,
                        ApplicationActionGrantRow.recipient_kind == recipient.kind,
                        ApplicationActionGrantRow.action == intent.action_id.value,
                    )
                )
                if recipient is not None
                else None
            )
            return InvitationAssignmentStateDTO(
                intent=intent,
                facts=ApplicationAccountGrantManagementFactsDTO(
                    installation_id=installation,
                    organization_id=organization,
                    project_id=project.project_id,
                    application_principal_id=target.application_principal_id,
                    action_id=intent.action_id,
                    access_revision=project.access_revision,
                    actor=project.action,
                    actor_can_grant=observed.actor_can_grant,
                    recipient=recipient,
                    recipient_is_project_member=member,
                    recipient_has_pending_recovery=pending,
                    recipient_has_coherent_identity=coherent,
                    assignment=ActionGrantState(can_grant=before),
                    grantors=grantors,
                ),
            )
        if isinstance(target, InvitationModelConnectionTargetDTO):
            grant = ModelConnectionActionGrantRow
            before = (
                await self._session.scalar(
                    select(grant.can_grant).where(
                        grant.project_id == project.project_id.value,
                        grant.model_connection_id == target.model_connection_id,
                        grant.recipient_principal_id == recipient.id.value,
                        grant.recipient_kind == recipient.kind,
                        grant.action == intent.action_id.value,
                    )
                )
                if recipient is not None
                else None
            )
            return InvitationAssignmentStateDTO(
                intent,
                ModelConnectionGrantFactsDTO(
                    installation,
                    organization,
                    project.project_id,
                    ModelConnectionId(target.model_connection_id),
                    ModelConnectionAction(intent.action_id.value),
                    project.access_revision,
                    project.action,
                    observed.actor_can_grant,
                    recipient,
                    member,
                    pending,
                    coherent,
                    False,
                    ActionGrantState(before),
                    grantors,
                ),
            )
        return None

    @staticmethod
    def _principal(row: PrincipalRow) -> Principal:
        return Principal(
            id=PrincipalId(row.id),
            organization_id=OrganizationId(row.organization_id),
            kind=row.kind,
            status=row.status,
        )

    @staticmethod
    def _grant_expression(intent: InvitationActionGrantIntentDTO) -> ColumnElement[bool]:
        target = intent.target
        if isinstance(target, OrganizationGrantTargetDTO):
            return (
                exists()
                .where(
                    OrganizationActionGrantRow.organization_id == target.organization_id.value,
                    OrganizationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    OrganizationActionGrantRow.recipient_kind == PrincipalRow.kind,
                    OrganizationActionGrantRow.action == intent.action_id.value,
                    OrganizationActionGrantRow.can_grant.is_(True),
                )
                .correlate(PrincipalRow)
            )
        if isinstance(target, ProjectGrantTargetDTO):
            return (
                exists()
                .where(
                    ProjectActionGrantRow.project_id == target.project_id.value,
                    ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                    ProjectActionGrantRow.action == intent.action_id.value,
                    ProjectActionGrantRow.can_grant.is_(True),
                )
                .correlate(PrincipalRow)
            )
        if isinstance(target, AccessGroupGrantTargetDTO):
            return (
                exists()
                .where(
                    GroupActionGrantRow.project_id == target.project_id.value,
                    GroupActionGrantRow.group_id == target.access_group_id.value,
                    GroupActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    GroupActionGrantRow.recipient_kind == PrincipalRow.kind,
                    GroupActionGrantRow.action == intent.action_id.value,
                    GroupActionGrantRow.can_grant.is_(True),
                )
                .correlate(PrincipalRow)
            )
        if isinstance(target, ApplicationAccountGrantTargetDTO):
            return (
                exists()
                .where(
                    ApplicationActionGrantRow.project_id == target.project_id.value,
                    ApplicationActionGrantRow.application_principal_id
                    == target.application_principal_id.value,
                    ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    ApplicationActionGrantRow.recipient_kind == PrincipalRow.kind,
                    ApplicationActionGrantRow.action == intent.action_id.value,
                    ApplicationActionGrantRow.can_grant.is_(True),
                )
                .correlate(PrincipalRow)
            )
        if isinstance(target, InvitationModelConnectionTargetDTO):
            grant = ModelConnectionActionGrantRow
            return (
                exists()
                .where(
                    grant.model_connection_id == target.model_connection_id,
                    grant.recipient_principal_id == PrincipalRow.id,
                    grant.recipient_kind == PrincipalRow.kind,
                    grant.action == intent.action_id.value,
                    grant.can_grant.is_(True),
                )
                .correlate(PrincipalRow)
            )
        raise RuntimeError("The assignment has no delivered Access grant target.")

    async def _grantors(
        self,
        intent: InvitationActionGrantIntentDTO,
        organization: OrganizationId,
        project: ProjectId,
        installation: InstallationId,
    ) -> tuple[ProjectDepartureCandidatePolicyInput, ...]:
        grant = self._grant_expression(intent)
        group_member = manager = literal(False)
        if isinstance(intent.target, AccessGroupGrantTargetDTO):
            group_member = (
                exists()
                .where(
                    GroupMembershipRow.project_id == project.value,
                    GroupMembershipRow.group_id == intent.target.access_group_id.value,
                    GroupMembershipRow.principal_id == PrincipalRow.id,
                )
                .correlate(PrincipalRow)
            )
            manager = (
                exists()
                .where(
                    GroupManagerRow.project_id == project.value,
                    GroupManagerRow.group_id == intent.target.access_group_id.value,
                    GroupManagerRow.principal_id == PrincipalRow.id,
                    GroupManagerRow.principal_kind == PrincipalRow.kind,
                )
                .correlate(PrincipalRow)
            )
        rows = (
            (
                await self._session.execute(
                    select(
                        PrincipalRow,
                        ProjectPrincipalQueries.pending(PrincipalRow.id, installation),
                        ProjectPrincipalQueries.membership(PrincipalRow.id, project, organization),
                        ProjectPrincipalQueries.coherent_identity(
                            PrincipalRow.id, organization, installation
                        ),
                        grant,
                        group_member,
                        manager,
                    )
                    .where(PrincipalRow.organization_id == organization.value, or_(grant, manager))
                    .execution_options(populate_existing=True, autoflush=False)
                )
            )
            .tuples()
            .all()
        )
        return tuple(
            ProjectDepartureCandidatePolicyInput(
                principal=self._principal(row),
                has_pending_recovery=pending,
                is_project_member=member,
                has_coherent_identity=coherent,
                can_grant=delegates,
                is_group_member=ordinary,
                is_group_manager=management,
            )
            for row, pending, member, coherent, delegates, ordinary, management in rows
        )
