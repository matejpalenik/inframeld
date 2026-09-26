"""Read current project facts while restricting records to the principal's organization."""

from typing import final, override

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.access_context import AccessContext
from inframeld_backend.access.application.authorization.action_facts_reader import ActionFactsReader
from inframeld_backend.access.application.authorization.current_action_facts import (
    CurrentActionFacts,
)
from inframeld_backend.access.application.authorization.project_action_target import (
    ProjectActionTarget,
)
from inframeld_backend.access.domain.action_values import ActionId
from inframeld_backend.access.infrastructure.postgres.models.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.postgres.models.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.postgres.models.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.access.infrastructure.postgres.models.project_row import ProjectRow


@final
class PostgresProjectActionFactsReader(ActionFactsReader):
    """Load typed statuses and relationship existence using the caller's session."""

    def __init__(self, session: AsyncSession) -> None:
        """Retain the caller-owned session without acquiring transaction ownership."""
        self._session = session

    @override
    async def read_action_facts(
        self, *, access: AccessContext, action: ActionId, target: ProjectActionTarget
    ) -> CurrentActionFacts | None:
        """Project stored facts into a DTO without deciding visibility or admission."""
        is_project_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )

        has_exact_action_grant = exists().where(
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == action.value,
        )

        statement = (
            select(
                PrincipalRow.status,
                ProjectRow.status,
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

        principal_status, project_status, member, granted = row

        return CurrentActionFacts(
            principal_status=principal_status,
            project_status=project_status,
            is_project_member=member,
            has_exact_action_grant=granted,
        )
