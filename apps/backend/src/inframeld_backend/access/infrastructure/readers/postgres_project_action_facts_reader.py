"""Read current project facts while restricting records to the principal's organization."""

from typing import final, override

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_action_facts_dto import ProjectActionFactsDTO
from inframeld_backend.access.application.dtos.project_action_target_dto import (
    ProjectActionTargetDTO,
)
from inframeld_backend.access.application.protocols.project_action_facts_reader import (
    ProjectActionFactsReader,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import ProjectMembershipRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow


@final
class PostgresProjectActionFactsReader(ProjectActionFactsReader):
    """Load typed statuses and relationship existence using the caller's session."""

    def __init__(self, session: AsyncSession) -> None:
        """Retain the caller-owned session without acquiring transaction ownership."""
        self._session = session

    @override
    async def read_action_facts(
        self, *, access: AccessContextDTO, action_id: ActionId, target: ProjectActionTargetDTO
    ) -> ProjectActionFactsDTO | None:
        """Project stored facts into a DTO without deciding visibility or admission."""
        is_project_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )

        has_exact_action_grant = exists().where(
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == action_id.value,
        )

        statement = (
            select(
                PrincipalRow.status,
                ProjectRow.status,
                ProjectRow.organization_id,
                is_project_member,
                has_exact_action_grant,
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == target.project_id.value,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .where(PrincipalRow.id == access.actor_principal_id.value)
        )

        result = await self._session.execute(statement)
        row = result.tuples().one_or_none()

        if row is None:
            return None

        principal_status, project_status, organization_id, member, granted = row

        return ProjectActionFactsDTO(
            organization_id=OrganizationId(organization_id),
            principal_status=principal_status,
            project_status=project_status,
            is_project_member=member,
            has_exact_action_grant=granted,
        )
