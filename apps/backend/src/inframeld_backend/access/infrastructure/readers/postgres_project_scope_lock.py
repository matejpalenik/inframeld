from uuid import UUID

from sqlalchemy import String, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.organization_row import OrganizationRow
from inframeld_backend.access.infrastructure.rows.principal_row import PrincipalRow
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow


class PostgresProjectScopeLock:
    """Coordinate scoped resource facts under the caller's Organization and Project turn."""

    @staticmethod
    async def acquire(
        session: AsyncSession, actor: PrincipalId, project: ProjectId, *, shared: bool
    ) -> UUID | None:
        if not session.in_transaction() or not session.is_active:
            raise RuntimeError("Project scope requires an active transaction.")
        isolation = await session.scalar(
            select(func.current_setting("transaction_isolation", type_=String()))
        )
        if isolation != "read committed":
            raise RuntimeError("Project scope requires READ COMMITTED isolation.")

        organization = await session.scalar(
            select(PrincipalRow.organization_id).where(PrincipalRow.id == actor.value)
        )
        if organization is None:
            return None

        locked_organization = await session.scalar(
            select(OrganizationRow.id)
            .where(OrganizationRow.id == organization)
            .with_for_update(read=True)
        )
        if locked_organization is None:
            return None
        locked_project = await session.scalar(
            select(ProjectRow.id)
            .where(ProjectRow.id == project.value, ProjectRow.organization_id == organization)
            .with_for_update(read=shared)
        )
        return organization if locked_project is not None else None
