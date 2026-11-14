import asyncio
from typing import override
from uuid import UUID

from sqlalchemy import String, exists, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.commands.issue_invitation_command import (
    IssueInvitationCommand,
)
from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_action_grant_intent_dto import (
    InvitationActionGrantIntentDTO,
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
from inframeld_backend.access.application.dtos.invitation_facts_dto import InvitationFactsDTO
from inframeld_backend.access.application.dtos.invitation_group_manager_intent_dto import (
    InvitationGroupManagerIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_group_membership_intent_dto import (
    InvitationGroupMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.application.dtos.invitation_project_membership_intent_dto import (
    InvitationProjectMembershipIntentDTO,
)
from inframeld_backend.access.application.dtos.invitation_record_dto import InvitationRecordDTO
from inframeld_backend.access.application.dtos.invitation_revocation_facts_dto import (
    InvitationRevocationFactsDTO,
)
from inframeld_backend.access.application.dtos.invitation_revocation_result_dto import (
    InvitationRevocationResultDTO,
)
from inframeld_backend.access.application.dtos.organization_grant_target_dto import (
    OrganizationGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.dtos.project_membership_observation_dto import (
    ProjectMembershipObservationDTO,
)
from inframeld_backend.access.application.protocols.invitation_facts_reader import (
    InvitationFactsReader,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.invitation_id import InvitationId
from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_invitation_mapper import (
    PostgresInvitationMapper,
)
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.model_connection_grant_queries import (
    ModelConnectionGrantQueries,
)
from inframeld_backend.access.infrastructure.readers.postgres_organization_access_facts_reader import (
    PostgresOrganizationAccessFactsReader,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
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
from inframeld_backend.access.infrastructure.rows.invitation_revocation_result_row import (
    InvitationRevocationResultRow,
)
from inframeld_backend.access.infrastructure.rows.invitation_row import InvitationRow
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.enums.http_method import HttpMethod
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

type _ProjectHeader = tuple[PrincipalRow, ProjectRow, UUID | None, bool, bool, bool, int | None]


class PostgresInvitationFactsReader(InvitationFactsReader):
    """Observe retained intent and current authority after the caller's ordered Access turns."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _record(row: InvitationRow) -> InvitationRecordDTO:
        return InvitationRecordDTO(
            invitation_id=InvitationId(row.id),
            organization_id=OrganizationId(row.organization_id),
            issuer_principal_id=PrincipalId(row.issuer_principal_id),
            digest=InvitationTokenDigest(row.token_digest),
            assignments=PostgresInvitationMapper.from_payload(row.assignments),
            issued_operation_id=OperationId(row.issued_operation_id),
            issued_access_revision=row.issued_access_revision,
            issued_at=row.issued_at,
            expires_at=row.expires_at,
            revoked_at=row.revoked_at,
            consumed_at=row.consumed_at,
            consumed_by_principal_id=PrincipalId(row.consumed_by_principal_id)
            if row.consumed_by_principal_id is not None
            else None,
        )

    @override
    async def read_by_digest(self, digest: InvitationTokenDigest) -> InvitationRecordDTO | None:
        try:
            row = await self._session.scalar(
                select(InvitationRow)
                .where(InvitationRow.token_digest == digest.value)
                .execution_options(populate_existing=True)
            )
            if row is None:
                return None
            if not InvitationTokenDigest(row.token_digest).matches(digest):
                raise DependencyUnavailableError()
            return self._record(row)
        except (
            TimeoutError,
            OperationalError,
            SqlAlchemyTimeoutError,
            TypeError,
            ValueError,
            KeyError,
        ):
            raise DependencyUnavailableError() from None

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

    async def model_projects(
        self, organization: OrganizationId, intents: tuple[InvitationAssignmentDTO, ...]
    ) -> dict[UUID, ProjectId]:
        return await ModelConnectionGrantQueries.invitation_projects(
            self._session,
            organization,
            tuple(
                intent.target
                for intent in intents
                if isinstance(intent, InvitationActionGrantIntentDTO)
                and isinstance(intent.target, InvitationModelConnectionTargetDTO)
            ),
        )

    @override
    async def lock_for_issue(
        self, *, access: AccessContextDTO, command: IssueInvitationCommand
    ) -> InvitationFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Invitation facts require the active caller transaction.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    if (
                        await self._session.scalar(
                            select(func.current_setting("transaction_isolation", type_=String()))
                        )
                        != "read committed"
                    ):
                        raise RuntimeError("Invitation coordination requires READ COMMITTED.")
                    organization = await self._session.scalar(
                        select(OrganizationRow.id)
                        .join(PrincipalRow, PrincipalRow.organization_id == OrganizationRow.id)
                        .where(
                            OrganizationRow.id == command.organization_id.value,
                            PrincipalRow.id == access.actor_principal_id.value,
                        )
                        .with_for_update(of=OrganizationRow)
                    )
                    if organization is None:
                        return None
                    projects = {
                        project
                        for intent in command.assignments
                        if (project := self._project_id(intent)) is not None
                    }
                    model_projects = await self.model_projects(
                        command.organization_id, command.assignments
                    )
                    projects.update(model_projects.values())
                    for project in sorted(projects, key=lambda value: value.value.int):
                        await self._session.scalar(
                            select(ProjectRow.id)
                            .where(
                                ProjectRow.id == project.value,
                                ProjectRow.organization_id == organization,
                            )
                            .with_for_update()
                        )
                    # Every decision observation follows all coordination waits.
                    actor = await PostgresOrganizationAccessFactsReader(self._session).read(
                        access=access
                    )
                    if actor is None:
                        return None
                    headers: dict[ProjectId, _ProjectHeader] = {}
                    for project in sorted(projects, key=lambda value: value.value.int):
                        header = (
                            (
                                await self._session.execute(
                                    ProjectActorQueries.header(access, project)
                                )
                            )
                            .tuples()
                            .one_or_none()
                        )
                        if header is not None:
                            if header[2] is None:
                                raise DependencyUnavailableError()
                            headers[project] = header
                    assignments = tuple(
                        [
                            await self._assignment(
                                access, intent, command.organization_id, headers, model_projects
                            )
                            for intent in command.assignments
                        ]
                    )
                    return InvitationFactsDTO(
                        organization_id=command.organization_id,
                        actor=actor,
                        assignments=assignments,
                    )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError() from None

    async def _assignment(
        self,
        access: AccessContextDTO,
        intent: InvitationAssignmentDTO,
        organization: OrganizationId,
        headers: dict[ProjectId, _ProjectHeader],
        model_projects: dict[UUID, ProjectId],
    ) -> InvitationAssignmentFactsDTO:
        project_id = (
            model_projects.get(intent.target.model_connection_id)
            if isinstance(intent, InvitationActionGrantIntentDTO)
            and isinstance(intent.target, InvitationModelConnectionTargetDTO)
            else self._project_id(intent)
        )
        project: ProjectMembershipObservationDTO | None = None
        target_exists = isinstance(intent, InvitationAdmissionOnlyIntentDTO) or (
            isinstance(intent, InvitationActionGrantIntentDTO)
            and isinstance(intent.target, OrganizationGrantTargetDTO)
            and intent.target.organization_id == organization
        )
        delegated = member = manager = False
        if project_id is not None and (header := headers.get(project_id)) is not None:
            principal_row, project_row, installation, actor_member, recovering, linked, version = (
                header
            )
            if installation is None:
                raise DependencyUnavailableError()
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
                        ProjectActionGrantRow.recipient_principal_id
                        == access.actor_principal_id.value,
                        ProjectActionGrantRow.recipient_kind == principal_row.kind,
                        ProjectActionGrantRow.action == action,
                    )
                )
                delegated = exact is True
                target_exists = True
            elif isinstance(
                intent, (InvitationGroupMembershipIntentDTO, InvitationGroupManagerIntentDTO)
            ) or (
                isinstance(intent, InvitationActionGrantIntentDTO)
                and isinstance(intent.target, AccessGroupGrantTargetDTO)
            ):
                if isinstance(intent, InvitationActionGrantIntentDTO):
                    if not isinstance(intent.target, AccessGroupGrantTargetDTO):
                        raise RuntimeError("The checked group intent changed its target kind.")
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
                                GroupMembershipRow.principal_id == access.actor_principal_id.value,
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
                                GroupManagerRow.principal_id == access.actor_principal_id.value,
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
                                == access.actor_principal_id.value,
                                GroupActionGrantRow.recipient_kind == principal_row.kind,
                                GroupActionGrantRow.action == intent.action_id.value,
                            )
                        )
                        is True
                    )
            elif isinstance(intent, InvitationActionGrantIntentDTO) and isinstance(
                intent.target, ApplicationAccountGrantTargetDTO
            ):
                application = intent.target.application_principal_id
                bound_member = exists().where(
                    ProjectMembershipRow.project_id == project_id.value,
                    ProjectMembershipRow.organization_id == organization.value,
                    ProjectMembershipRow.principal_id == application.value,
                    ProjectMembershipRow.application_principal_id == application.value,
                    ProjectMembershipRow.principal_kind == PrincipalKind.APPLICATION,
                )
                target_exists = (
                    await self._session.scalar(
                        select(ApplicationAccountRow.principal_id)
                        .join(PrincipalRow, PrincipalRow.id == ApplicationAccountRow.principal_id)
                        .where(
                            ApplicationAccountRow.principal_id == application.value,
                            ApplicationAccountRow.project_id == project_id.value,
                            ApplicationAccountRow.organization_id == organization.value,
                            ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                            PrincipalRow.organization_id == organization.value,
                            PrincipalRow.kind == PrincipalKind.APPLICATION,
                            PrincipalRow.status == PrincipalStatus.ACTIVE,
                            bound_member,
                        )
                    )
                    is not None
                )
                delegated = (
                    await self._session.scalar(
                        select(ApplicationActionGrantRow.can_grant).where(
                            ApplicationActionGrantRow.project_id == project_id.value,
                            ApplicationActionGrantRow.application_principal_id == application.value,
                            ApplicationActionGrantRow.recipient_principal_id
                            == access.actor_principal_id.value,
                            ApplicationActionGrantRow.recipient_kind == principal_row.kind,
                            ApplicationActionGrantRow.action == intent.action_id.value,
                        )
                    )
                    is True
                )
            elif isinstance(intent, InvitationActionGrantIntentDTO) and isinstance(
                intent.target, InvitationModelConnectionTargetDTO
            ):
                target_exists, delegated = await ModelConnectionGrantQueries.invitation_authority(
                    self._session,
                    organization,
                    project_id,
                    intent.target,
                    access.actor_principal_id,
                    principal_row.kind,
                    intent.action_id,
                )
            project = ProjectMembershipObservationDTO(
                installation_id=InstallationId(installation),
                organization_id=organization,
                project_id=project_id,
                access_revision=project_row.access_revision,
                action=PostgresProjectActorMapper.action(
                    access=access,
                    principal=principal_row,
                    project=project_row,
                    member=actor_member,
                    recovering=recovering,
                    linked=linked,
                    version=version,
                    granted=exact is not None,
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
    async def read_issue_original(
        self,
        *,
        organization_id: OrganizationId,
        issuer_principal_id: PrincipalId,
        operation_id: OperationId,
    ) -> InvitationRecordDTO | None:
        """Match the recovered native original, without reconstructing or exposing its secret."""
        try:
            row = await self._session.scalar(
                select(InvitationRow)
                .join(
                    IdempotencyReservationRow,
                    IdempotencyReservationRow.operation_id == InvitationRow.issued_operation_id,
                )
                .where(
                    InvitationRow.issued_operation_id == operation_id.value,
                    InvitationRow.organization_id == organization_id.value,
                    InvitationRow.issuer_principal_id == issuer_principal_id.value,
                    IdempotencyReservationRow.organization_id == organization_id.value,
                    IdempotencyReservationRow.principal_id == issuer_principal_id.value,
                    IdempotencyReservationRow.project_id.is_(None),
                    IdempotencyReservationRow.method == HttpMethod.POST.value,
                    IdempotencyReservationRow.requested_route == "/v1/invitations",
                    IdempotencyReservationRow.lookup_authority_family.is_(None),
                    IdempotencyReservationRow.lookup_action_id.is_(None),
                    IdempotencyReservationRow.state == OperationReservationState.REPLAYABLE,
                    IdempotencyReservationRow.replay_kind == OperationReplayKind.ISSUED_SECRET,
                    IdempotencyReservationRow.expires_at.is_not(None),
                )
                .execution_options(populate_existing=True)
            )
            return None if row is None else self._record(row)
        except (
            TimeoutError,
            OperationalError,
            SqlAlchemyTimeoutError,
            TypeError,
            ValueError,
            KeyError,
        ):
            raise DependencyUnavailableError() from None

    @override
    async def lock_for_revocation(
        self, *, access: AccessContextDTO, invitation_id: InvitationId
    ) -> InvitationRevocationFactsDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Revocation facts require the active caller transaction.")
        try:
            async with asyncio.timeout(5):
                with self._session.no_autoflush:
                    if (
                        await self._session.scalar(
                            select(func.current_setting("transaction_isolation", type_=String()))
                        )
                        != "read committed"
                    ):
                        raise RuntimeError("Revocation coordination requires READ COMMITTED.")
                    organization = await self._session.scalar(
                        select(OrganizationRow.id)
                        .join(InvitationRow, InvitationRow.organization_id == OrganizationRow.id)
                        .join(PrincipalRow, PrincipalRow.organization_id == OrganizationRow.id)
                        .where(
                            InvitationRow.id == invitation_id.value,
                            PrincipalRow.id == access.actor_principal_id.value,
                        )
                        .with_for_update(of=OrganizationRow)
                    )
                    if organization is None:
                        return None
                    # Revocation needs current administration, never the promised assignment turns.
                    actor = await PostgresOrganizationAccessFactsReader(self._session).read(
                        access=access
                    )
                    row = await self._session.scalar(
                        select(InvitationRow)
                        .where(
                            InvitationRow.id == invitation_id.value,
                            InvitationRow.organization_id == organization,
                        )
                        .execution_options(populate_existing=True, autoflush=False)
                    )
                    if actor is None or row is None:
                        return None
                    return InvitationRevocationFactsDTO(
                        organization_id=OrganizationId(organization),
                        actor=actor,
                        invitation=self._record(row),
                    )
        except (
            TimeoutError,
            OperationalError,
            SqlAlchemyTimeoutError,
            TypeError,
            ValueError,
            KeyError,
        ):
            raise DependencyUnavailableError() from None

    @override
    async def read_revocation_original(
        self,
        *,
        organization_id: OrganizationId,
        actor_principal_id: PrincipalId,
        invitation_id: InvitationId,
        operation_id: OperationId,
    ) -> InvitationRevocationResultDTO | None:
        result, parent = InvitationRevocationResultRow, IdempotencyReservationRow
        try:
            async with asyncio.timeout(5):
                loaded = (
                    (
                        await self._session.execute(
                            select(result, parent.expires_at)
                            .join(parent, parent.operation_id == result.operation_id)
                            .where(
                                result.operation_id == operation_id.value,
                                result.organization_id == organization_id.value,
                                result.actor_principal_id == actor_principal_id.value,
                                result.invitation_id == invitation_id.value,
                                parent.organization_id == result.organization_id,
                                parent.principal_id == result.actor_principal_id,
                                parent.project_id.is_(None),
                                parent.method == HttpMethod.POST.value,
                                parent.requested_route
                                == f"/v1/invitations/{invitation_id.value}/revoke",
                                parent.lookup_authority_family.is_(None),
                                parent.lookup_action_id.is_(None),
                                parent.state == OperationReservationState.REPLAYABLE,
                                parent.replay_kind == OperationReplayKind.SAFE_RESULT,
                                parent.expires_at > func.clock_timestamp(),
                            )
                            .execution_options(populate_existing=True, autoflush=False)
                        )
                    )
                    .tuples()
                    .one_or_none()
                )
                if loaded is None:
                    return None
                row, expiry = loaded
                if (
                    expiry is None
                    or expiry.utcoffset() is None
                    or row.access_revision != row.before_revision + int(row.changed)
                ):
                    raise DependencyUnavailableError()
                RevisionValidation.require(row.before_revision)
                RevisionValidation.require(row.access_revision)
                return InvitationRevocationResultDTO(
                    invitation_id=invitation_id,
                    organization_id=organization_id,
                    access_revision=row.access_revision,
                    operation=CompletedSynchronousOperationDTO(
                        operation_id=operation_id,
                        created=False,
                        replay_kind=OperationReplayKind.SAFE_RESULT,
                        expires_at=expiry,
                    ),
                )
        except (TimeoutError, OperationalError, SqlAlchemyTimeoutError, TypeError, ValueError):
            raise DependencyUnavailableError() from None
