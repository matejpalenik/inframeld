from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.artifact_cleanup_facts_dto import (
    ArtifactCleanupFactsDTO,
)
from inframeld_backend.shared.application.protocols.artifact_cleanup_facts_reader import (
    ArtifactCleanupFactsReader,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_cleanup_obligation_id import (
    ArtifactCleanupObligationId,
)
from inframeld_backend.shared.application.value_objects.job_id import JobId
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_target_row import (
    ArtifactCleanupTargetRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow


class PostgresArtifactCleanupFactsReader(ArtifactCleanupFactsReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, obligation_id: ArtifactCleanupObligationId
    ) -> ArtifactCleanupFactsDTO | None:
        if not self._session.in_transaction():
            raise RuntimeError("Cleanup authority facts require the protected caller transaction.")
        obligation = await self._session.scalar(
            select(ArtifactCleanupObligationRow)
            .where(ArtifactCleanupObligationRow.id == obligation_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        job = await self._session.scalar(
            select(DurableJobRow).where(DurableJobRow.cleanup_obligation_id == obligation_id.value)
        )
        if obligation is None or job is None or job.binding_kind != "artifact_cleanup":
            return None
        targets = tuple(
            await self._session.scalars(
                select(ArtifactAttemptRow)
                .join(
                    ArtifactCleanupTargetRow,
                    ArtifactCleanupTargetRow.attempt_id == ArtifactAttemptRow.id,
                )
                .where(ArtifactCleanupTargetRow.obligation_id == obligation.id)
                .order_by(ArtifactAttemptRow.id)
                .with_for_update(of=ArtifactAttemptRow)
                .execution_options(populate_existing=True)
            )
        )
        binding = PostgresJobBindingMapper.cleanup(obligation)
        owned = bool(targets) and all(
            (target.installation_id, target.organization_id, target.project_id)
            == (
                binding.scope.installation_id.value,
                binding.scope.organization_id.value,
                binding.scope.project_id.value,
            )
            for target in targets
        )
        return ArtifactCleanupFactsDTO(
            binding,
            JobId(job.id),
            tuple(ArtifactAttemptId(target.id) for target in targets),
            owned,
            obligation.retirement_authorized and all(target.retired for target in targets),
            not any(target.retention_protected for target in targets),
            any(target.published for target in targets),
            any(target.put_pending for target in targets),
            obligation.physically_complete,
        )
