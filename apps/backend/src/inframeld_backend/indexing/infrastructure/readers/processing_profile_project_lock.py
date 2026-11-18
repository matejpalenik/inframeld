from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.value_objects.principal_id import PrincipalId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.access.infrastructure.readers.postgres_project_scope_lock import (
    PostgresProjectScopeLock,
)


class ProcessingProfileProjectLock:
    """Keep human identity and Project authority coherent through the profile operation."""

    @staticmethod
    async def acquire(
        session: AsyncSession, actor: PrincipalId, project: ProjectId, *, shared: bool
    ) -> UUID | None:
        return await PostgresProjectScopeLock.acquire(session, actor, project, shared=shared)
