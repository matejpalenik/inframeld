from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.rows.model_connection_row import ModelConnectionRow
from inframeld_backend.shared.application.value_objects.model_connection_id import ModelConnectionId


class ModelConnectionReferenceQueries:
    """Observe the owning Project's live connection for retained configuration references."""

    @staticmethod
    async def has_live_target(
        session: AsyncSession,
        organization: OrganizationId,
        project: ProjectId,
        connection_id: ModelConnectionId,
    ) -> bool:
        """Require the caller's exclusive Project lock through commit."""
        if not session.in_transaction() or not session.is_active:
            raise RuntimeError("Model Connection reference lookup requires a caller transaction.")

        connection = await session.scalar(
            select(ModelConnectionRow.id)
            .where(
                ModelConnectionRow.id == connection_id.value,
                ModelConnectionRow.organization_id == organization.value,
                ModelConnectionRow.project_id == project.value,
                ModelConnectionRow.retired_at.is_(None),
            )
            .execution_options(autoflush=False)
        )
        return connection is not None
