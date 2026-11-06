from typing import override

from sqlalchemy import Nullable, exists, select, true
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.access_group_action_grant_dto import (
    AccessGroupActionGrantDTO,
)
from inframeld_backend.access.application.dtos.access_group_action_grants_page_facts_dto import (
    AccessGroupActionGrantsPageFactsDTO,
)
from inframeld_backend.access.application.protocols.access_group_action_grants_facts_reader import (
    AccessGroupActionGrantsFactsReader,
)
from inframeld_backend.access.domain.value_objects.access_group_id import AccessGroupId
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
from inframeld_backend.access.infrastructure.rows.access_group_row import AccessGroupRow
from inframeld_backend.access.infrastructure.rows.group_action_grant_row import GroupActionGrantRow
from inframeld_backend.access.infrastructure.rows.group_manager_row import GroupManagerRow
from inframeld_backend.access.infrastructure.rows.group_membership_row import GroupMembershipRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresAccessGroupActionGrantsFactsReader(AccessGroupActionGrantsFactsReader):
    """Keep exact group authority and stored recipients in the same bounded snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        group_id: AccessGroupId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> AccessGroupActionGrantsPageFactsDTO | None:
        assignment = aliased(GroupActionGrantRow, name="stored_assignment")
        page = select(assignment).where(
            assignment.project_id == ProjectRow.id,
            assignment.group_id == AccessGroupRow.id,
            assignment.action == action_id.value,
        )
        if after is not None:
            page = page.where(assignment.recipient_principal_id > after.value)
        bounded = (
            page.order_by(assignment.recipient_principal_id)
            .limit(limit + 1)
            .correlate(ProjectRow, AccessGroupRow)
            .lateral("assignments_page")
        )
        stored = aliased(GroupActionGrantRow, bounded)
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
        member = (
            exists()
            .where(
                GroupMembershipRow.project_id == ProjectRow.id,
                GroupMembershipRow.group_id == AccessGroupRow.id,
                GroupMembershipRow.principal_id == PrincipalRow.id,
            )
            .correlate(PrincipalRow, ProjectRow, AccessGroupRow)
        )
        manager = (
            exists()
            .where(
                GroupManagerRow.project_id == ProjectRow.id,
                GroupManagerRow.group_id == AccessGroupRow.id,
                GroupManagerRow.principal_id == PrincipalRow.id,
                GroupManagerRow.principal_kind == PrincipalRow.kind,
            )
            .correlate(PrincipalRow, ProjectRow, AccessGroupRow)
        )
        statement = (
            ProjectActorQueries.header(access, project_id)
            .join(AccessGroupRow, AccessGroupRow.project_id == ProjectRow.id)
            .where(AccessGroupRow.id == group_id.value)
            .outerjoin(bounded, true())
            .add_columns(
                granted.label("actor_has_exact_action_grant"),
                granted.where(GroupActionGrantRow.can_grant.is_(True)).label(
                    "actor_can_grant_action"
                ),
                member,
                manager,
                Nullable(stored),
            )
            .order_by(stored.recipient_principal_id)
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
            pending,
            linked,
            version,
            has_grant,
            can_grant,
            group_member,
            group_manager,
            _,
        ) = rows[0]
        if installed is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")

        return AccessGroupActionGrantsPageFactsDTO(
            installation_id=InstallationId(installed),
            organization_id=OrganizationId(principal.organization_id),
            project_id=ProjectId(project.id),
            group_id=group_id,
            action_id=action_id,
            actor_can_grant=can_grant,
            actor=PostgresProjectActorMapper.action(
                access=access,
                principal=principal,
                project=project,
                member=project_member,
                recovering=pending,
                linked=linked,
                version=version,
                granted=has_grant,
            ),
            actor_is_group_member=group_member,
            actor_is_group_manager=group_manager,
            items=tuple(
                AccessGroupActionGrantDTO(
                    recipient_principal_id=PrincipalId(item.recipient_principal_id),
                    action_id=ActionId(item.action),
                    can_grant=item.can_grant,
                )
                for _, _, _, _, _, _, _, _, _, _, _, item in rows
                if item is not None
            ),
        )
