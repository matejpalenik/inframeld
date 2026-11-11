from datetime import datetime
from typing import override
from uuid import UUID

from sqlalchemy import DateTime, Nullable, String, and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.project_deletion_job_facts_dto import (
    ProjectDeletionJobFactsDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.project_deletion_job_facts_reader import (
    ProjectDeletionJobFactsReader,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.application.value_objects.job_payload import JobPayload
from inframeld_backend.shared.infrastructure.mappers.postgres_deletion_status_mapper import (
    PostgresDeletionStatusMapper,
)
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.rows.deletion_status_binding_row import (
    DeletionStatusBindingRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.project_deletion_obligation_row import (
    ProjectDeletionObligationRow,
)


class PostgresProjectDeletionJobFactsReader(ProjectDeletionJobFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(self, obligation_id: UUID) -> ProjectDeletionJobFactsDTO | None:
        """Observe the retained original and validate any present original child.

        Original job references after local completion confer no live execution authority.
        """
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deletion backing requires its caller transaction.")
        if (
            await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            != "read committed"
        ):
            raise RuntimeError("Deletion backing requires READ COMMITTED isolation.")
        stored = (
            (
                await self._session.execute(
                    select(
                        ProjectDeletionObligationRow,
                        Nullable(DurableJobRow),
                        DeletionStatusBindingRow,
                        func.clock_timestamp(type_=DateTime(timezone=True)),
                    )
                    .select_from(ProjectDeletionObligationRow)
                    .outerjoin(
                        DurableJobRow, DurableJobRow.id == ProjectDeletionObligationRow.job_id
                    )
                    .join(
                        DeletionStatusBindingRow,
                        DeletionStatusBindingRow.operation_id
                        == ProjectDeletionObligationRow.operation_id,
                    )
                    .where(ProjectDeletionObligationRow.id == obligation_id)
                    .execution_options(populate_existing=True, autoflush=False)
                )
            )
            .tuples()
            .one_or_none()
        )
        if stored is None:
            return None
        parent, job, original, now = stored
        binding = PostgresJobBindingMapper.project_deletion(parent)
        payload = JobPayload("project.application-shutdown", 1, parent.id.bytes)
        if job is None:
            if parent.shutdown_completed_at is None:
                raise DependencyUnavailableError(
                    "The original shutdown child is unavailable before completion."
                )
        elif (
            job.id,
            job.binding_kind,
            job.deletion_obligation_id,
            job.installation_id,
            job.organization_id,
            job.project_id,
            job.request_id,
            job.admitted_at,
            job.payload_kind,
            job.payload_version,
            job.payload,
        ) != (
            parent.job_id,
            "project_deletion",
            parent.id,
            parent.installation_id,
            parent.organization_id,
            parent.project_id,
            parent.request_id,
            parent.admitted_at,
            payload.kind,
            payload.version,
            payload.data,
        ) or any(
            value is not None
            for value in (
                job.operation_id,
                job.cleanup_obligation_id,
                job.principal_id,
                job.principal_kind,
                job.action_id,
                job.human_authority,
                job.human_subject,
                job.human_version,
            )
        ):
            raise ConflictError("The original deletion child binding is incoherent.")
        return ProjectDeletionJobFactsDTO(
            binding,
            JobId(parent.job_id),
            payload,
            PostgresDeletionStatusMapper.to_binding(original),
            parent.admitted_at,
            now,
            parent.source_revision,
            parent.shutdown_completed_at,
            parent.physical_cleanup_completed_at,
        )

    async def pending_physical(
        self, *, limit: int, after: tuple[datetime, UUID] | None = None
    ) -> tuple[ProjectDeletionJobFactsDTO, ...]:
        """Read a capped indexed handoff of committed local shutdowns still physically pending.

        This observation grants no physical cleanup or execution authority.
        Preserve original attribution and never expire or requeue the parent.
        """
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("The physical handoff page must contain between one and 100 rows.")
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Deletion handoff requires its caller transaction.")
        if after is not None and after[0].utcoffset() is None:
            raise ValueError("The internal handoff cursor requires an aware original timestamp.")
        query = select(ProjectDeletionObligationRow.id).where(
            ProjectDeletionObligationRow.shutdown_completed_at.is_not(None),
            ProjectDeletionObligationRow.physical_cleanup_completed_at.is_(None),
        )
        if after is not None:
            admitted_at, identifier = after
            query = query.where(
                or_(
                    ProjectDeletionObligationRow.admitted_at > admitted_at,
                    and_(
                        ProjectDeletionObligationRow.admitted_at == admitted_at,
                        ProjectDeletionObligationRow.id > identifier,
                    ),
                )
            )
        identifiers = tuple(
            await self._session.scalars(
                query.order_by(
                    ProjectDeletionObligationRow.admitted_at, ProjectDeletionObligationRow.id
                ).limit(limit)
            )
        )
        observed: list[ProjectDeletionJobFactsDTO] = []
        for identifier in identifiers:
            facts = await self.read(identifier)
            if facts is None:
                raise ConflictError("A retained physical handoff disappeared.")
            observed.append(facts)
        return tuple(observed)
