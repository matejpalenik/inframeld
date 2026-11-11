from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.project_deletion_result_dto import (
    ProjectDeletionResultDTO,
)
from inframeld_backend.access.application.protocols.project_deletion_result_reader import (
    ProjectDeletionResultReader,
)
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_deletion_obligation_id import (
    ProjectDeletionObligationId,
)
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.dtos.accepted_async_operation_dto import (
    AcceptedAsyncOperationDTO,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.services.project_deletion_job_authorization_service import (
    ProjectDeletionJobAuthorizationService,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.readers.postgres_project_deletion_job_facts_reader import (
    PostgresProjectDeletionJobFactsReader,
)
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)


class PostgresProjectDeletionResultReader(ProjectDeletionResultReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def original(
        self,
        *,
        installation_id: InstallationId,
        organization_id: OrganizationId,
        project_id: ProjectId,
        actor_principal_id: PrincipalId,
        operation: AcceptedAsyncOperationDTO,
    ) -> ProjectDeletionResultDTO:
        """Read the immutable original after current ordinary Delete-project authorization.

        Verify the retained reservation, obligation, job and original human
        binding. Missing or incoherent required history fails closed rather than
        reconstructing acceptance from today's Project. Use caller transaction
        and deadline. Narrow initiator-only content-free status stays separate.
        """
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deletion original requires its caller transaction.")
        row = await self._session.scalar(
            select(ProjectDeletionObligationRow)
            .where(
                ProjectDeletionObligationRow.operation_id == operation.operation_id.value,
                ProjectDeletionObligationRow.installation_id == installation_id.value,
                ProjectDeletionObligationRow.organization_id == organization_id.value,
                ProjectDeletionObligationRow.project_id == project_id.value,
                ProjectDeletionObligationRow.initiator_principal_id == actor_principal_id.value,
            )
            .execution_options(populate_existing=True)
        )
        if row is None:
            raise ConflictError("The original Project-deletion acceptance is unavailable.")
        await ProjectDeletionJobAuthorizationService(
            PostgresProjectDeletionJobFactsReader(self._session)
        ).require_current(JobId(row.job_id), PostgresJobBindingMapper.project_deletion(row))
        return ProjectDeletionResultDTO(
            installation_id,
            organization_id,
            project_id,
            actor_principal_id,
            ProjectDeletionObligationId(row.id),
            JobId(row.job_id),
            row.before_access_revision,
            row.access_revision,
            operation,
        )
