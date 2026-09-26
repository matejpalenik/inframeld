from typing import final

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.access_authorizer import (
    AccessContext,
    ActionFactsReader,
    ActionTarget,
    CurrentActionFacts,
)
from inframeld_backend.access.domain.authorization import ActionAuthorizationFacts
from inframeld_backend.access.infrastructure.persistence_models import (
    PrincipalRow,
    ProjectActionGrantRow,
    ProjectMembershipRow,
    ProjectRow,
)

_HIDDEN_TARGET_FACTS = CurrentActionFacts(
    authorization=ActionAuthorizationFacts(
        principal_is_active=False,
        is_project_member=False,
        has_exact_action_grant=False,
    ),
    target_is_visible=False,
)


@final
class PostgresProjectActionFactsReader(ActionFactsReader):
    """Read project visibility and action grants using an existing database session."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read_action_facts(
        self, *, access: AccessContext, action: str, target: ActionTarget
    ) -> CurrentActionFacts:
        """Return current access facts for a project target"""

        if target.target_kind != "project" or target.target_id != target.project_id:
            return _HIDDEN_TARGET_FACTS

        is_project_member = exists().where(
            ProjectMembershipRow.project_id == ProjectRow.id,
            ProjectMembershipRow.principal_id == PrincipalRow.id,
        )

        has_exact_action_grant = exists().where(
            ProjectActionGrantRow.project_id == ProjectRow.id,
            ProjectActionGrantRow.recipient_principal_id == PrincipalRow.id,
            ProjectActionGrantRow.action == action,
        )

        statement = (
            select(
                (PrincipalRow.status == "active").label("principal_is_active"),
                is_project_member.label("is_project_member"),
                has_exact_action_grant.label("has_exact_action_grant"),
                and_(
                    ProjectRow.status == "active",
                    PrincipalRow.status == "active",
                    is_project_member,
                ).label("target_is_visible"),
            )
            .select_from(PrincipalRow)
            .join(
                ProjectRow,
                and_(
                    ProjectRow.id == target.project_id,
                    ProjectRow.organization_id == PrincipalRow.organization_id,
                ),
            )
            .where(PrincipalRow.id == access.actor_principal_id)
        )

        result = await self._session.execute(statement)
        row = result.mappings().one_or_none()

        if row is None:
            return _HIDDEN_TARGET_FACTS

        return CurrentActionFacts(
            authorization=ActionAuthorizationFacts(
                principal_is_active=bool(row["principal_is_active"]),
                is_project_member=bool(row["is_project_member"]),
                has_exact_action_grant=bool(row["has_exact_action_grant"]),
            ),
            target_is_visible=bool(row["target_is_visible"]),
        )
