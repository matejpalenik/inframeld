from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.pipelines.domain.value_objects.pipeline_id import PipelineId
from inframeld_backend.pipelines.infrastructure.rows.pipeline_row import PipelineRow
from inframeld_backend.releases.infrastructure.rows.deployment_row import DeploymentRow
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresDeploymentAssociationReader:
    """Observe Deployment association under the owning Build transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def require_absent(self, *, scope: ArtifactScopeDTO, pipeline_id: PipelineId) -> None:
        """Check all associations while holding the Project turn through admission.

        The caller checks Build authority and takes the Project turn for update
        before reading configuration or other scoped resources. Releases uses
        the same turn to create or change a Deployment association.
        """
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deployment association requires an active transaction.")
        connection = await self._session.connection()
        if await connection.get_isolation_level() != "READ COMMITTED":
            raise RuntimeError("Deployment association requires READ COMMITTED.")

        project = await self._session.scalar(
            select(ProjectRow.id)
            .where(
                ProjectRow.id == scope.project_id.value,
                ProjectRow.organization_id == scope.organization_id.value,
                ProjectRow.status == ProjectStatus.ACTIVE,
                exists().where(
                    InstallationIdentityRow.singleton_key == 1,
                    InstallationIdentityRow.installation_id == scope.installation_id.value,
                ),
            )
            .with_for_update()
        )
        if project is None:
            raise ResourceNotFoundError()

        associated = await self._session.scalar(
            select(
                exists().where(
                    DeploymentRow.installation_id == scope.installation_id.value,
                    DeploymentRow.organization_id == scope.organization_id.value,
                    DeploymentRow.project_id == project,
                    DeploymentRow.pipeline_id == pipeline_id.value,
                )
            )
            .select_from(PipelineRow)
            .where(
                PipelineRow.installation_id == scope.installation_id.value,
                PipelineRow.organization_id == scope.organization_id.value,
                PipelineRow.project_id == project,
                PipelineRow.id == pipeline_id.value,
            )
        )
        if associated is None:
            raise ResourceNotFoundError()
        if associated:
            raise ConflictError("The reviewed Pipeline now has a Deployment association.")
