from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.knowledge.infrastructure.rows.document_version_row import DocumentVersionRow
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_content_digest import (
    ArtifactContentDigest,
)
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow


class PostgresSealedPdfSourceReader:
    """Read the exact published PDF seal for the owning workflow's authorized source."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(
        self, scope: ArtifactScopeDTO, version_id: DocumentVersionId
    ) -> ArtifactAttemptDTO | None:
        """Read storage facts without granting access or retaining a processing pin."""
        version = DocumentVersionRow
        attempt = ArtifactAttemptRow
        statement = (
            select(attempt.artifact_id, attempt.id, version.length, version.digest)
            .select_from(version)
            .join(
                attempt,
                and_(
                    attempt.id == version.attempt_id,
                    attempt.installation_id == version.installation_id,
                    attempt.organization_id == version.organization_id,
                    attempt.project_id == version.project_id,
                    attempt.length == version.length,
                    attempt.digest == version.digest,
                ),
            )
            .where(
                version.id == version_id.value,
                version.installation_id == scope.installation_id.value,
                version.organization_id == scope.organization_id.value,
                version.project_id == scope.project_id.value,
                version.media_type == "application/pdf",
                attempt.state == "published",
                attempt.published.is_(True),
                attempt.put_confirmed.is_(True),
                attempt.retired.is_(False),
                attempt.remote_removed.is_(False),
            )
        )
        seal = (await self._session.execute(statement)).tuples().one_or_none()
        if seal is None:
            return None
        artifact_id, attempt_id, length, digest = seal
        return ArtifactAttemptDTO(
            ArtifactId(artifact_id),
            ArtifactAttemptId(attempt_id),
            scope,
            length,
            ArtifactContentDigest(digest),
        )
