from typing import override

from sqlalchemy import ColumnElement, Nullable, and_, exists, literal, or_, select, true
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_grant_target_dto import (
    AccessGroupGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.application_account_grant_target_dto import (
    ApplicationAccountGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.grant_recipient_candidate_dto import (
    GrantRecipientCandidateDTO,
)
from inframeld_backend.access.application.dtos.grant_recipients_page_facts_dto import (
    GrantRecipientsPageFactsDTO,
)
from inframeld_backend.access.application.dtos.model_connection_grant_target_dto import (
    ModelConnectionGrantTargetDTO,
)
from inframeld_backend.access.application.dtos.project_grant_target_dto import ProjectGrantTargetDTO
from inframeld_backend.access.application.protocols.grant_recipients_facts_reader import (
    GrantRecipientsFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.access.domain.value_objects.access_group_relationships import (
    AccessGroupRelationships,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.mappers.postgres_project_actor_mapper import (
    PostgresProjectActorMapper,
)
from inframeld_backend.access.infrastructure.readers.project_actor_queries import (
    ProjectActorQueries,
)
from inframeld_backend.access.infrastructure.readers.project_principal_queries import (
    ProjectPrincipalQueries,
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
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
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


class PostgresGrantRecipientsFactsReader(GrantRecipientsFactsReader):
    """Observe current authority and eligible choices in one PostgreSQL snapshot.

    Catalogue kinds and current eligibility constrain the lateral query before
    its UUID position and limit. The left join preserves authorization facts
    when that eligible continuation is empty.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        target: ProjectGrantTargetDTO
        | AccessGroupGrantTargetDTO
        | ApplicationAccountGrantTargetDTO
        | ModelConnectionGrantTargetDTO,
        action_id: ActionId,
        eligible_kinds: tuple[PrincipalKind, ...],
        after: PrincipalId | None,
        limit: int,
    ) -> GrantRecipientsPageFactsDTO | None:
        header = ProjectActorQueries.header(access, project_id).where(
            ProjectRow.id == target.project_id.value
        )
        group_member: ColumnElement[bool] = literal(False)
        group_manager: ColumnElement[bool] = literal(False)
        if isinstance(target, ProjectGrantTargetDTO):
            granted = (
                exists()
                .where(
                    ProjectActionGrantRow.project_id == ProjectRow.id,
                    ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    ProjectActionGrantRow.recipient_kind == PrincipalRow.kind,
                    ProjectActionGrantRow.action == action_id.value,
                )
                .correlate(PrincipalRow, ProjectRow)
            )
            delegated = granted.where(ProjectActionGrantRow.can_grant.is_(True))
        elif isinstance(target, AccessGroupGrantTargetDTO):
            header = header.join(AccessGroupRow, AccessGroupRow.project_id == ProjectRow.id).where(
                AccessGroupRow.id == target.access_group_id.value
            )
            granted = (
                exists()
                .where(
                    GroupActionGrantRow.project_id == ProjectRow.id,
                    GroupActionGrantRow.group_id == AccessGroupRow.id,
                    GroupActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    GroupActionGrantRow.recipient_kind == PrincipalRow.kind,
                    GroupActionGrantRow.action == action_id.value,
                )
                .correlate(PrincipalRow, ProjectRow, AccessGroupRow)
            )
            delegated = granted.where(GroupActionGrantRow.can_grant.is_(True))
            group_member = (
                exists()
                .where(
                    GroupMembershipRow.project_id == ProjectRow.id,
                    GroupMembershipRow.group_id == AccessGroupRow.id,
                    GroupMembershipRow.principal_id == PrincipalRow.id,
                )
                .correlate(PrincipalRow, ProjectRow, AccessGroupRow)
            )
            group_manager = (
                exists()
                .where(
                    GroupManagerRow.project_id == ProjectRow.id,
                    GroupManagerRow.group_id == AccessGroupRow.id,
                    GroupManagerRow.principal_id == PrincipalRow.id,
                    GroupManagerRow.principal_kind == PrincipalRow.kind,
                )
                .correlate(PrincipalRow, ProjectRow, AccessGroupRow)
            )
        elif isinstance(target, ModelConnectionGrantTargetDTO):
            header = header.join(
                ModelConnectionRow,
                and_(
                    ModelConnectionRow.project_id == ProjectRow.id,
                    ModelConnectionRow.organization_id == ProjectRow.organization_id,
                ),
            ).where(
                ModelConnectionRow.id == target.model_connection_id.value,
                ModelConnectionRow.retired_at.is_(None),
            )
            model_grants = ModelConnectionActionGrantRow
            granted = (
                exists()
                .where(
                    model_grants.project_id == ProjectRow.id,
                    model_grants.model_connection_id == ModelConnectionRow.id,
                    model_grants.recipient_principal_id == PrincipalRow.id,
                    model_grants.recipient_kind == PrincipalRow.kind,
                    model_grants.action == action_id.value,
                )
                .correlate(PrincipalRow, ProjectRow, ModelConnectionRow)
            )
            delegated = granted.where(model_grants.can_grant.is_(True))
        else:
            application = aliased(PrincipalRow, name="application_principal")
            bound_membership = (
                exists()
                .where(
                    ProjectMembershipRow.project_id == ProjectRow.id,
                    ProjectMembershipRow.organization_id == PrincipalRow.organization_id,
                    ProjectMembershipRow.principal_id == application.id,
                    ProjectMembershipRow.principal_kind == PrincipalKind.APPLICATION,
                    ProjectMembershipRow.application_principal_id == application.id,
                )
                .correlate(PrincipalRow, ProjectRow, application)
            )
            header = (
                header.join(
                    ApplicationAccountRow,
                    and_(
                        ApplicationAccountRow.project_id == ProjectRow.id,
                        ApplicationAccountRow.organization_id == PrincipalRow.organization_id,
                        ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
                    ),
                )
                .join(
                    application,
                    and_(
                        application.id == ApplicationAccountRow.principal_id,
                        application.organization_id == ApplicationAccountRow.organization_id,
                        application.kind == PrincipalKind.APPLICATION,
                        application.status == PrincipalStatus.ACTIVE,
                    ),
                )
                .where(
                    ApplicationAccountRow.principal_id == target.application_principal_id.value,
                    bound_membership,
                )
            )
            granted = (
                exists()
                .where(
                    ApplicationActionGrantRow.project_id == ProjectRow.id,
                    ApplicationActionGrantRow.application_principal_id
                    == ApplicationAccountRow.principal_id,
                    ApplicationActionGrantRow.recipient_principal_id == PrincipalRow.id,
                    ApplicationActionGrantRow.recipient_kind == PrincipalRow.kind,
                    ApplicationActionGrantRow.action == action_id.value,
                )
                .correlate(PrincipalRow, ProjectRow, ApplicationAccountRow)
            )
            delegated = granted.where(ApplicationActionGrantRow.can_grant.is_(True))

        candidate = aliased(PrincipalRow, name="eligible_recipient")
        membership = aliased(ProjectMembershipRow, name="eligible_membership")
        pending = ProjectPrincipalQueries.pending(
            candidate.id, InstallationIdentityRow.installation_id
        )
        coherent = ProjectPrincipalQueries.coherent_identity(
            candidate.id, PrincipalRow.organization_id, InstallationIdentityRow.installation_id
        )
        bound = (
            exists()
            .where(
                ApplicationAccountRow.principal_id == candidate.id,
                ApplicationAccountRow.project_id == ProjectRow.id,
                ApplicationAccountRow.organization_id == PrincipalRow.organization_id,
                ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
            )
            .correlate_except(ApplicationAccountRow)
        )
        page = (
            select(candidate)
            .join(
                membership,
                and_(
                    membership.principal_id == candidate.id,
                    membership.principal_kind == candidate.kind,
                    membership.organization_id == candidate.organization_id,
                    membership.project_id == ProjectRow.id,
                ),
            )
            .where(
                candidate.organization_id == PrincipalRow.organization_id,
                candidate.status == PrincipalStatus.ACTIVE,
                candidate.kind.in_(eligible_kinds),
                or_(
                    and_(candidate.kind == PrincipalKind.HUMAN, ~pending, coherent),
                    and_(
                        candidate.kind == PrincipalKind.APPLICATION,
                        membership.application_principal_id == candidate.id,
                        bound,
                    ),
                ),
            )
        )
        if after is not None:
            page = page.where(candidate.id > after.value)
        bounded = (
            page.order_by(candidate.id)
            .limit(limit + 1)
            .correlate(PrincipalRow, ProjectRow, InstallationIdentityRow)
            .lateral("eligible_recipients_page")
        )
        recipient = aliased(PrincipalRow, bounded)
        observed_pending = ProjectPrincipalQueries.pending(
            recipient.id, InstallationIdentityRow.installation_id
        )
        observed_coherent = ProjectPrincipalQueries.coherent_identity(
            recipient.id, PrincipalRow.organization_id, InstallationIdentityRow.installation_id
        )
        observed_bound = (
            exists()
            .where(
                ApplicationAccountRow.principal_id == recipient.id,
                ApplicationAccountRow.project_id == ProjectRow.id,
                ApplicationAccountRow.organization_id == PrincipalRow.organization_id,
                ApplicationAccountRow.principal_kind == PrincipalKind.APPLICATION,
            )
            .correlate_except(ApplicationAccountRow)
        )
        statement = (
            header.outerjoin(bounded, true())
            .add_columns(
                granted.label("actor_has_exact_action_grant"),
                delegated.label("actor_can_grant_action"),
                group_member,
                group_manager,
                Nullable(recipient),
                observed_pending,
                observed_coherent,
                observed_bound,
            )
            .order_by(recipient.id)
        )
        try:
            rows = (await self._session.execute(statement)).tuples().all()
        except (OperationalError, SqlAlchemyTimeoutError) as error:
            raise DependencyUnavailableError() from error
        if not rows:
            return None
        (
            principal,
            project,
            installed,
            project_member,
            recovering,
            linked,
            version,
            has_grant,
            can_grant,
            member,
            manager,
            _,
            _,
            _,
            _,
        ) = rows[0]
        if installed is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")

        return GrantRecipientsPageFactsDTO(
            installation_id=InstallationId(installed),
            organization_id=OrganizationId(principal.organization_id),
            project_id=ProjectId(project.id),
            target=target,
            action_id=action_id,
            actor=PostgresProjectActorMapper.action(
                access=access,
                principal=principal,
                project=project,
                member=project_member,
                recovering=recovering,
                linked=linked,
                version=version,
                granted=has_grant,
            ),
            actor_can_grant=can_grant,
            actor_group_relationships=AccessGroupRelationships(member=member, manager=manager)
            if isinstance(target, AccessGroupGrantTargetDTO)
            else None,
            items=tuple(
                GrantRecipientCandidateDTO(
                    principal=Principal(
                        id=PrincipalId(item.id),
                        organization_id=OrganizationId(item.organization_id),
                        kind=item.kind,
                        status=item.status,
                    ),
                    display_name=item.display_name,
                    is_project_member=True,
                    has_pending_recovery=blocked,
                    has_coherent_identity=identity,
                    application_is_project_bound=application_bound,
                )
                for _, _, _, _, _, _, _, _, _, _, _, item, blocked, identity, application_bound in rows
                if item is not None
            ),
        )
