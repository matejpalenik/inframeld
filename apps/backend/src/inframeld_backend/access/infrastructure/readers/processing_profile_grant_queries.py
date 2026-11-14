from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.invitation_processing_profile_target_dto import (
    InvitationProcessingProfileTargetDTO,
)
from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.indexing.infrastructure.rows.processing_profile_action_grant_row import (
    ProcessingProfileActionGrantRow,
)
from inframeld_backend.indexing.infrastructure.rows.processing_profile_row import (
    ProcessingProfileRow,
)


class ProcessingProfileGrantQueries:
    """Observe the real same-Organization owner of an invitation's stable profile ID."""

    @staticmethod
    async def invitation_projects(
        session: AsyncSession,
        organization: OrganizationId,
        targets: tuple[InvitationProcessingProfileTargetDTO, ...],
    ) -> dict[UUID, ProjectId]:
        if not targets:
            return {}
        rows = (
            await session.execute(
                select(ProcessingProfileRow.id, ProcessingProfileRow.project_id).where(
                    ProcessingProfileRow.organization_id == organization.value,
                    ProcessingProfileRow.id.in_(
                        [target.processing_profile_id for target in targets]
                    ),
                )
            )
        ).tuples()
        return {profile: ProjectId(project) for profile, project in rows}

    @staticmethod
    async def invitation_authority(
        session: AsyncSession,
        organization: OrganizationId,
        project: ProjectId,
        target: InvitationProcessingProfileTargetDTO,
        actor: PrincipalId,
        kind: PrincipalKind,
        action: ActionId,
    ) -> tuple[bool, bool]:
        grant = ProcessingProfileActionGrantRow
        row = (
            (
                await session.execute(
                    select(ProcessingProfileRow.id, grant.can_grant)
                    .outerjoin(
                        grant,
                        (grant.project_id == ProcessingProfileRow.project_id)
                        & (grant.processing_profile_id == ProcessingProfileRow.id)
                        & (grant.recipient_principal_id == actor.value)
                        & (grant.recipient_kind == kind)
                        & (grant.action == action.value),
                    )
                    .where(
                        ProcessingProfileRow.organization_id == organization.value,
                        ProcessingProfileRow.project_id == project.value,
                        ProcessingProfileRow.id == target.processing_profile_id,
                    )
                )
            )
            .tuples()
            .one_or_none()
        )
        return (False, False) if row is None else (True, row[1] is True)
