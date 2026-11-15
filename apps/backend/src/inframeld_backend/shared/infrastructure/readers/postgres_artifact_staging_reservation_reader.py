import asyncio
from typing import override

from sqlalchemy import DateTime, func, select
from sqlalchemy.exc import InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as SqlAlchemyTimeoutError

from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.protocols.artifact_staging_reservation_reader import (
    ArtifactStagingReservationReader,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.infrastructure.mappers.postgres_artifact_attempt_mapper import (
    PostgresArtifactAttemptMapper,
)
from inframeld_backend.shared.infrastructure.resources.database import Database
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)


class PostgresArtifactStagingReservationReader(ArtifactStagingReservationReader):
    """Close one fresh five-second session before any local or remote content work."""

    def __init__(self, database: Database) -> None:
        self._database = database

    @override
    async def read(
        self, reservation_id: ArtifactStagingReservationId
    ) -> ArtifactStagingReservationDTO | None:
        return await self._read(reservation_id=reservation_id)

    @override
    async def read_attempt(
        self, attempt_id: ArtifactAttemptId
    ) -> ArtifactStagingReservationDTO | None:
        return await self._read(attempt_id=attempt_id)

    async def _read(
        self,
        *,
        reservation_id: ArtifactStagingReservationId | None = None,
        attempt_id: ArtifactAttemptId | None = None,
    ) -> ArtifactStagingReservationDTO | None:
        statement = select(
            ArtifactAttemptRow,
            ArtifactStagingReservationRow,
            func.clock_timestamp(type_=DateTime(timezone=True)),
        ).join(
            ArtifactStagingReservationRow,
            ArtifactStagingReservationRow.attempt_id == ArtifactAttemptRow.id,
        )
        if reservation_id is not None:
            statement = statement.where(ArtifactStagingReservationRow.id == reservation_id.value)
        elif attempt_id is not None:
            statement = statement.where(ArtifactAttemptRow.id == attempt_id.value)
        else:
            raise RuntimeError("An exact original reservation identity is required.")
        try:
            async with asyncio.timeout(5.0), self._database.session() as session:
                result = (await session.execute(statement)).tuples().one_or_none()
                return (
                    PostgresArtifactAttemptMapper.reservation(*result)
                    if result is not None
                    else None
                )
        except (TimeoutError, InterfaceError, OperationalError, SqlAlchemyTimeoutError):
            raise DependencyUnavailableError(
                "The original local reservation is unavailable."
            ) from None
