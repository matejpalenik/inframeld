import asyncio
from datetime import timedelta
from typing import override

from sqlalchemy import DateTime, Nullable, func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.deletion_status_authorization_dto import (
    DeletionStatusAuthorizationDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_obligation_provenance_dto import (
    DeletionStatusObligationProvenanceDTO,
)
from inframeld_backend.shared.application.dtos.deletion_status_observation_dto import (
    DeletionStatusObservationDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.deletion_status_projection_reader import (
    DeletionStatusProjectionReader,
)
from inframeld_backend.shared.application.services.project_deletion_job_authorization_service import (
    ProjectDeletionJobAuthorizationService,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.infrastructure.mappers.postgres_deletion_status_mapper import (
    PostgresDeletionStatusMapper,
)
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.readers.postgres_project_deletion_job_facts_reader import (
    PostgresProjectDeletionJobFactsReader,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_observation_row import (
    DeletionStatusObservationRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)


class PostgresDeletionStatusReader(DeletionStatusProjectionReader):
    """Read exact retained initiator scope within the caller's coordinated transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, *, authorization: DeletionStatusAuthorizationDTO
    ) -> DeletionStatusObservationDTO | None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deletion status requires an active caller transaction.")

        binding = DeletionStatusBindingRow
        statement = (
            select(
                binding,
                Nullable(DeletionStatusObservationRow),
                func.clock_timestamp(type_=DateTime(timezone=True)),
            )
            .select_from(binding)
            .outerjoin(
                DeletionStatusObservationRow,
                DeletionStatusObservationRow.operation_id == binding.operation_id,
            )
            .where(
                binding.operation_id == authorization.operation_id.value,
                binding.installation_id == authorization.installation_id.value,
                binding.organization_id == authorization.organization_id.value,
                binding.initiator_principal_id == authorization.principal_id.value,
            )
            .execution_options(populate_existing=True)
        )
        try:
            async with asyncio.timeout(5):
                stored = (await self._session.execute(statement)).tuples().one_or_none()
                if stored is None:
                    return None

                retained, owner, observed_at = stored
                parent = await self._session.scalar(
                    select(ProjectDeletionObligationRow)
                    .where(
                        ProjectDeletionObligationRow.operation_id == retained.operation_id,
                        ProjectDeletionObligationRow.installation_id == retained.installation_id,
                        ProjectDeletionObligationRow.organization_id == retained.organization_id,
                        ProjectDeletionObligationRow.project_id == retained.project_id,
                        ProjectDeletionObligationRow.initiator_principal_id
                        == retained.initiator_principal_id,
                    )
                    .execution_options(populate_existing=True)
                )
                if parent is None:
                    return PostgresDeletionStatusMapper.to_observation(retained, owner, observed_at)
                facts = await ProjectDeletionJobAuthorizationService(
                    PostgresProjectDeletionJobFactsReader(self._session)
                ).require_current(
                    JobId(parent.job_id), PostgresJobBindingMapper.project_deletion(parent)
                )
                job = await self._session.get(DurableJobRow, parent.job_id, populate_existing=True)
                if job is None and facts.shutdown_completed_at is None:
                    raise DependencyUnavailableError()
                physical = facts.physical_cleanup_completed_at
                return DeletionStatusObservationDTO(
                    binding=facts.original,
                    observed_at=facts.observed_at,
                    owner_revision=facts.source_revision,
                    owner_observed_at=facts.observed_at,
                    job_status=JobStatus(job.status) if job is not None else None,
                    admission_confirmed=True,
                    access_blocked=True,
                    application_shutdown_complete=facts.shutdown_completed_at is not None,
                    physical_cleanup_complete=physical is not None,
                    unfinished_obligation=DeletionStatusObligationProvenanceDTO(
                        parent.id,
                        facts.binding.operation_id,
                        facts.binding.installation_id,
                        authorization.organization_id,
                        facts.original.project_id,
                        authorization.principal_id,
                        facts.observed_at,
                        facts.source_revision,
                    )
                    if physical is None
                    else None,
                    retention_started_at=physical,
                    expires_at=physical + timedelta(days=facts.original.retention_days)
                    if physical is not None and facts.original.retention_days is not None
                    else None,
                )
        except (
            TimeoutError,
            OperationalError,
            SqlAlchemyTimeoutError,
            TypeError,
            ValueError,
            LookupError,
        ):
            raise DependencyUnavailableError() from None
