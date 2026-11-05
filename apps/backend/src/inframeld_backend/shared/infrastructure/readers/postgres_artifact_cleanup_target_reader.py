from typing import override

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.protocols.artifact_cleanup_target_reader import (
    ArtifactCleanupTargetReader,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
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


class PostgresArtifactCleanupTargetReader(ArtifactCleanupTargetReader):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def read(
        self, binding: ArtifactCleanupJobBindingDTO, attempt_id: ArtifactAttemptId
    ) -> ArtifactCleanupTargetDTO | None:
        if not self._session.in_transaction():
            raise RuntimeError("Cleanup targets require their protected caller transaction.")
        obligation = await self._session.scalar(
            select(ArtifactCleanupObligationRow)
            .where(ArtifactCleanupObligationRow.id == binding.obligation_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if obligation is None or PostgresJobBindingMapper.cleanup(obligation) != binding:
            return None
        target = await self._session.scalar(
            select(ArtifactAttemptRow)
            .join(
                ArtifactCleanupTargetRow,
                ArtifactCleanupTargetRow.attempt_id == ArtifactAttemptRow.id,
            )
            .where(
                ArtifactCleanupTargetRow.obligation_id == binding.obligation_id.value,
                ArtifactAttemptRow.id == attempt_id.value,
                ArtifactAttemptRow.installation_id == binding.scope.installation_id.value,
                ArtifactAttemptRow.organization_id == binding.scope.organization_id.value,
                ArtifactAttemptRow.project_id == binding.scope.project_id.value,
            )
            .with_for_update(of=ArtifactAttemptRow)
            .execution_options(populate_existing=True)
        )
        if target is None:
            return None
        if (target.length is None) != (target.digest is None):
            raise ConflictError("The original sealed expectation is incomplete.")
        return ArtifactCleanupTargetDTO(
            ArtifactId(target.artifact_id),
            ArtifactAttemptId(target.id),
            ArtifactScopeDTO(
                binding.scope.installation_id,
                binding.scope.organization_id,
                binding.scope.project_id,
            ),
            target.length,
            ArtifactContentDigest(target.digest) if target.digest is not None else None,
        )
