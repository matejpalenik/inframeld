from typing import override

from sqlalchemy import Nullable, and_, exists, select, true
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.application_account_action_grant_dto import (
    ApplicationAccountActionGrantDTO,
)
from inframeld_backend.access.application.dtos.application_account_action_grants_page_facts_dto import (
    ApplicationAccountActionGrantsPageFactsDTO,
)
from inframeld_backend.access.application.protocols.application_account_action_grants_facts_reader import (
    ApplicationAccountActionGrantsFactsReader,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
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
from inframeld_backend.access.infrastructure.rows.application_account_row import (
    ApplicationAccountRow,
)
from inframeld_backend.access.infrastructure.rows.application_action_grant_row import (
    ApplicationActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresApplicationAccountActionGrantsFactsReader(ApplicationAccountActionGrantsFactsReader):
    """Observe a live Project-bound account and its stored grants in one snapshot."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_page(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        application_principal_id: PrincipalId,
        action_id: ActionId,
        after: PrincipalId | None,
        limit: int,
    ) -> ApplicationAccountActionGrantsPageFactsDTO | None:
        application = aliased(PrincipalRow, name="application_principal")
        assignment = aliased(ApplicationActionGrantRow, name="stored_assignment")
        page = select(assignment).where(
            assignment.project_id == ProjectRow.id,
            assignment.application_principal_id == ApplicationAccountRow.principal_id,
            assignment.action == action_id.value,
        )
        if after is not None:
            page = page.where(assignment.recipient_principal_id > after.value)
        bounded = (
            page.order_by(assignment.recipient_principal_id)
            .limit(limit + 1)
            .correlate(ProjectRow, ApplicationAccountRow)
            .lateral("assignments_page")
        )
        stored = aliased(ApplicationActionGrantRow, bounded)
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
        statement = (
            ProjectActorQueries.header(access, project_id)
            .join(
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
                ApplicationAccountRow.principal_id == application_principal_id.value,
                bound_membership,
            )
            .outerjoin(bounded, true())
            .add_columns(
                granted.label("actor_has_exact_action_grant"),
                granted.where(ApplicationActionGrantRow.can_grant.is_(True)).label(
                    "actor_can_grant_action"
                ),
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
            _,
        ) = rows[0]
        if installed is None:
            raise DependencyUnavailableError("The installation identity is unavailable.")

        return ApplicationAccountActionGrantsPageFactsDTO(
            installation_id=InstallationId(installed),
            organization_id=OrganizationId(principal.organization_id),
            project_id=ProjectId(project.id),
            application_principal_id=application_principal_id,
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
            items=tuple(
                ApplicationAccountActionGrantDTO(
                    recipient_principal_id=PrincipalId(item.recipient_principal_id),
                    action_id=ActionId(item.action),
                    can_grant=item.can_grant,
                )
                for _, _, _, _, _, _, _, _, _, item in rows
                if item is not None
            ),
        )
