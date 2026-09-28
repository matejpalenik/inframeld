"""Read current grant facts while holding the Access change locks."""

from typing import final, override

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.access_context_dto import AccessContextDTO
from inframeld_backend.access.application.dtos.project_grant_change_facts_dto import (
    ProjectGrantChangeFactsDTO,
)
from inframeld_backend.access.application.protocols.project_grant_change_facts_reader import (
    ProjectGrantChangeFactsReader,
)
from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_action_grant_row import (
    ProjectActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.project_membership_row import (
    ProjectMembershipRow,
)
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow


def _to_principal(row: PrincipalRow) -> Principal:
    return Principal(
        id=PrincipalId(row.id),
        organization_id=OrganizationId(row.organization_id),
        kind=row.kind,
        status=row.status,
    )


@final
class PostgresProjectGrantChangeFactsReader(ProjectGrantChangeFactsReader):
    """Use the caller's session; the caller owns commit or rollback."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read_for_change(
        self,
        *,
        access: AccessContextDTO,
        project_id: ProjectId,
        recipient_principal_id: PrincipalId,
        action_id: ActionId,
    ) -> ProjectGrantChangeFactsDTO | None:
        # Locate the actor's organization. Re-read the actor after locking it.
        actor_organization_id = await self._session.scalar(
            select(PrincipalRow.organization_id).where(
                PrincipalRow.id == access.actor_principal_id.value
            )
        )
        if actor_organization_id is None:
            return None

        # Access changes take the organization lock before the project lock.
        locked_organization_id = await self._session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == actor_organization_id)
            .with_for_update(read=True)
        )
        if locked_organization_id is None:
            return None

        project_result = await self._session.execute(
            select(ProjectRow.status, ProjectRow.access_revision)
            .where(
                ProjectRow.id == project_id.value,
                ProjectRow.organization_id == locked_organization_id,
            )
            .with_for_update()
        )
        project = project_result.tuples().one_or_none()
        if project is None:
            return None

        project_status, project_access_revision = project

        actor_row = await self._session.scalar(
            select(PrincipalRow).where(
                PrincipalRow.id == access.actor_principal_id.value,
                PrincipalRow.organization_id == locked_organization_id,
            )
        )
        if actor_row is None:
            return None

        recipient_row = await self._session.scalar(
            select(PrincipalRow).where(
                PrincipalRow.id == recipient_principal_id.value,
                PrincipalRow.organization_id == locked_organization_id,
            )
        )

        actor_is_member = (
            await self._session.scalar(
                select(
                    exists().where(
                        ProjectMembershipRow.project_id == project_id.value,
                        ProjectMembershipRow.principal_id == actor_row.id,
                    )
                )
            )
            is True
        )

        recipient_is_member = False
        if recipient_row is not None:
            recipient_is_member = (
                await self._session.scalar(
                    select(
                        exists().where(
                            ProjectMembershipRow.project_id == project_id.value,
                            ProjectMembershipRow.principal_id == recipient_row.id,
                        )
                    )
                )
                is True
            )

        actor_can_grant = (
            await self._session.scalar(
                select(
                    exists().where(
                        ProjectActionGrantRow.project_id == project_id.value,
                        ProjectActionGrantRow.recipient_principal_id == actor_row.id,
                        ProjectActionGrantRow.action == action_id.value,
                        ProjectActionGrantRow.can_grant.is_(True),
                    )
                )
            )
            is True
        )

        return ProjectGrantChangeFactsDTO(
            actor=_to_principal(actor_row),
            recipient=_to_principal(recipient_row) if recipient_row is not None else None,
            project_status=project_status,
            project_access_revision=project_access_revision,
            actor_is_project_member=actor_is_member,
            recipient_is_project_member=recipient_is_member,
            actor_can_grant_action=actor_can_grant,
        )
