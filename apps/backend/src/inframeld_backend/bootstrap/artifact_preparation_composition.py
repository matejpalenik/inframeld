import asyncio
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import override

from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.artifact_preparation_records import (
    ArtifactPreparationRecords,
)
from inframeld_backend.shared.application.services.artifact_preparation_service import (
    ArtifactPreparationService,
)
from inframeld_backend.shared.infrastructure.readers.postgres_artifact_staging_reservation_reader import (
    PostgresArtifactStagingReservationReader,
)
from inframeld_backend.shared.infrastructure.repositories.postgres_artifact_attempt_repository import (
    PostgresArtifactAttemptRepository,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.resources.private_artifact_preparation import (
    PrivateArtifactPreparation,
)
from inframeld_backend.shared.infrastructure.resources.private_artifact_staging import (
    PrivateArtifactStaging,
)
from inframeld_backend.shared.infrastructure.resources.s3_artifact_store import S3ArtifactStore
from inframeld_backend.shared.infrastructure.settings.artifact_staging_settings import (
    ArtifactStagingSettings,
)
from inframeld_backend.shared.infrastructure.settings.artifact_storage_settings import (
    ArtifactStorageSettings,
)


class _PreparationRecords(ArtifactPreparationRecords):
    def __init__(self, database: Database) -> None:
        self._database = database

    @asynccontextmanager
    async def _session(self) -> AsyncGenerator[AsyncSession]:
        try:
            async with asyncio.timeout(5.0), self._database.session() as session, session.begin():
                yield session
        except (TimeoutError, InterfaceError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError(
                "The original preparation state cannot be confirmed."
            ) from None

    @override
    async def inspect(self, allocation: ArtifactAllocationDTO) -> ArtifactStagingReservationDTO:
        async with self._session() as session:
            return await PostgresArtifactAttemptRepository(session).inspect(allocation)

    @override
    async def seal(self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO) -> None:
        async with self._session() as session:
            await PostgresArtifactAttemptRepository(session).seal(allocation, attempt)

    @override
    async def begin_put(
        self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO
    ) -> bool:
        async with self._session() as session:
            return await PostgresArtifactAttemptRepository(session).begin_put(allocation, attempt)

    @override
    async def confirm_verified(
        self, allocation: ArtifactAllocationDTO, verified: VerifiedArtifactDTO
    ) -> None:
        async with self._session() as session:
            await PostgresArtifactAttemptRepository(session).confirm_verified(allocation, verified)


async def create_artifact_preparation(
    database: Database,
    staging_settings: ArtifactStagingSettings,
    storage_settings: ArtifactStorageSettings,
) -> ArtifactPreparationService:
    """Open private metadata custody before allocation and supply an internal storage entrypoint.

    The caller owns the process database pool and existing allocator. Each private
    prepare/resume invocation owns its separate S3 client and complete drain.
    No route, audience authority or DocumentVersion is created here.
    """
    staging = PrivateArtifactStaging(
        staging_settings.root, PostgresArtifactStagingReservationReader(database)
    )
    await staging.startup()
    return ArtifactPreparationService(
        _PreparationRecords(database),
        PrivateArtifactPreparation(staging, lambda: S3ArtifactStore(storage_settings)),
    )
