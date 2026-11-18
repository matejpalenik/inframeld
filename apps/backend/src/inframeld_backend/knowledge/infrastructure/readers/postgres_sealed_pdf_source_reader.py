from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.value_objects.document_version_id import DocumentVersionId
from inframeld_backend.knowledge.infrastructure.rows.document_row import DocumentRow
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
        return await self._read(scope, version_id, lock_document=False)

    async def read_for_publication(
        self, scope: ArtifactScopeDTO, version_id: DocumentVersionId
    ) -> ArtifactAttemptDTO | None:
        """Guard publication from an erasure marker in the caller's active transaction.

        Check current authority first under the caller's Organization and Project
        locks. Take this Document turn before queue, job or artifact locks, keep
        it through commit, and do no external I/O while holding it.
        """
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("PDF source publication requires an active transaction.")
        connection = await self._session.connection()
        if await connection.get_isolation_level() != "READ COMMITTED":
            raise RuntimeError("PDF source publication requires READ COMMITTED.")

        if await self._read(scope, version_id, lock_document=True) is None:
            return None
        # A joined artifact observation can predate time spent waiting for the Document lock.
        return await self.read(scope, version_id)

    async def _read(
        self, scope: ArtifactScopeDTO, version_id: DocumentVersionId, *, lock_document: bool
    ) -> ArtifactAttemptDTO | None:
        document = DocumentRow
        version = DocumentVersionRow
        attempt = ArtifactAttemptRow
        statement = (
            select(attempt.artifact_id, attempt.id, version.length, version.digest)
            .select_from(version)
            .join(
                document,
                and_(
                    document.id == version.document_id,
                    document.installation_id == version.installation_id,
                    document.organization_id == version.organization_id,
                    document.project_id == version.project_id,
                ),
            )
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
                document.erasure_operation_id.is_(None),
                document.erasure_blocked_at.is_(None),
                attempt.state == "published",
                attempt.published.is_(True),
                attempt.put_confirmed.is_(True),
                attempt.retired.is_(False),
                attempt.remote_removed.is_(False),
            )
        )
        if lock_document:
            statement = statement.with_for_update(read=True, of=document)
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
