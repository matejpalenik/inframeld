from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.invitation_model_connection_target_dto import (
    InvitationModelConnectionTargetDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.model_connection_action_grant_row import (
    ModelConnectionActionGrantRow,
)
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow


class ModelConnectionGrantQueries:
    """Observe the real same-Organization owner of an invitation's stable model ID."""

    @staticmethod
    async def invitation_projects(
        session: AsyncSession,
        organization: OrganizationId,
        targets: tuple[InvitationModelConnectionTargetDTO, ...],
    ) -> dict[UUID, ProjectId]:
        if not targets:
            return {}
        rows = (
            await session.execute(
                select(ModelConnectionRow.id, ModelConnectionRow.project_id).where(
                    ModelConnectionRow.organization_id == organization.value,
                    ModelConnectionRow.id.in_([target.model_connection_id for target in targets]),
                )
            )
        ).tuples()
        return {connection: ProjectId(project) for connection, project in rows}

    @staticmethod
    async def invitation_authority(
        session: AsyncSession,
        organization: OrganizationId,
        project: ProjectId,
        target: InvitationModelConnectionTargetDTO,
        actor: PrincipalId,
        kind: PrincipalKind,
        action: ActionId,
    ) -> tuple[bool, bool]:
        grant = ModelConnectionActionGrantRow
        row = (
            (
                await session.execute(
                    select(ModelConnectionRow.id, grant.can_grant)
                    .outerjoin(
                        grant,
                        (grant.project_id == ModelConnectionRow.project_id)
                        & (grant.model_connection_id == ModelConnectionRow.id)
                        & (grant.recipient_principal_id == actor.value)
                        & (grant.recipient_kind == kind)
                        & (grant.action == action.value),
                    )
                    .where(
                        ModelConnectionRow.organization_id == organization.value,
                        ModelConnectionRow.project_id == project.value,
                        ModelConnectionRow.id == target.model_connection_id,
                        ModelConnectionRow.retired_at.is_(None),
                    )
                )
            )
            .tuples()
            .one_or_none()
        )
        return (False, False) if row is None else (True, row[1] is True)
