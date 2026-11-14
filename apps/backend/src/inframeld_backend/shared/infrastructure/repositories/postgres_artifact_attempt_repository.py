import math
from datetime import timedelta
from typing import override

from sqlalchemy import DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactReservationError,
)
from inframeld_backend.shared.application.protocols.artifact_attempt_repository import (
    ArtifactAttemptRepository,
)
from inframeld_backend.shared.application.protocols.artifact_capacity_reader import (
    ArtifactCapacityReader,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.infrastructure.mappers.postgres_artifact_attempt_mapper import (
    PostgresArtifactAttemptMapper,
)
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresArtifactAttemptRepository(ArtifactAttemptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def reserve(
        self,
        *,
        scope: ArtifactScopeDTO,
        artifact_id: ArtifactId,
        attempt_id: ArtifactAttemptId,
        reservation_id: ArtifactStagingReservationId,
        limit_bytes: int,
        transfer_seconds: float,
        capacity_reader: ArtifactCapacityReader,
    ) -> ArtifactStagingReservationDTO:
        if not self._session.in_transaction():
            raise RuntimeError("Artifact allocation requires its caller transaction.")
        if (
            type(limit_bytes) is not int
            or not 0 < limit_bytes <= 256 * 1024 * 1024
            or not math.isfinite(transfer_seconds)
            or not 0 < transfer_seconds <= 7200
        ):
            raise ArtifactCapacityError("The allocation exceeds the fixed artifact bounds.")

        # Match Access's Project-before-queue lock order for new scoped growth.
        project = await self._session.scalar(
            select(ProjectRow)
            .where(
                ProjectRow.id == scope.project_id.value,
                ProjectRow.organization_id == scope.organization_id.value,
            )
            .with_for_update()
        )
        installation = await self._session.scalar(select(InstallationIdentityRow.installation_id))
        if project is None or installation != scope.installation_id.value:
            raise ArtifactReservationError("The allocation scope cannot be confirmed.")
        queue = await self._session.scalar(
            select(ApplicationJobQueueRow)
            .where(ApplicationJobQueueRow.singleton_key == 1)
            .with_for_update()
        )
        if queue is None:
            raise ArtifactReservationError("The shared queue is unavailable.")
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise ArtifactReservationError("The authoritative allocation clock is unavailable.")

        existing = await self._session.get(ArtifactStagingReservationRow, reservation_id.value)
        if existing is not None:
            attempt = await self._session.get(ArtifactAttemptRow, existing.attempt_id)
            if (
                attempt is None
                or attempt.id != attempt_id.value
                or attempt.artifact_id != artifact_id.value
                or (attempt.installation_id, attempt.organization_id, attempt.project_id)
                != (
                    scope.installation_id.value,
                    scope.organization_id.value,
                    scope.project_id.value,
                )
                or existing.limit_bytes != limit_bytes
                or existing.expires_at - attempt.created_at != timedelta(seconds=transfer_seconds)
            ):
                raise ArtifactReservationError("The allocation retry changed its original meaning.")
            return PostgresArtifactAttemptMapper.reservation(attempt, existing, now)
        if project.status is not ProjectStatus.ACTIVE:
            raise ArtifactReservationError("New private bytes require an active Project.")
        ledger = await self._session.scalar(
            select(ArtifactStorageCapacityRow)
            .where(ArtifactStorageCapacityRow.installation_id == scope.installation_id.value)
            .with_for_update()
        )
        # The queue lock also serializes a first allocation without a ledger row.
        capacity = await capacity_reader.read()
        if (
            any(
                type(value) is not int or value < 0
                for value in (
                    capacity.usable_bytes,
                    capacity.free_bytes,
                    capacity.backup_reserved_bytes,
                )
            )
            or not capacity.usable_bytes
            or capacity.free_bytes > capacity.usable_bytes
        ):
            raise ArtifactCapacityError("Physical capacity cannot be confirmed.")

        if ledger is None:
            ledger = ArtifactStorageCapacityRow(installation_id=scope.installation_id.value)
            self._session.add(ledger)
        projected = ledger.protected_reserved_bytes + 2 * limit_bytes
        pending_growth = ledger.protected_reserved_bytes - ledger.occupied_bytes
        # Unknown partial copies stay conservatively charged. Reserve room for
        # a full protected backup independently of the private spool ceiling.
        backup = max(capacity.backup_reserved_bytes, projected)
        projected_free = capacity.free_bytes - pending_growth - 2 * limit_bytes - backup
        if (
            ledger.spool_reserved_bytes + limit_bytes > 2 * 1024**3
            or projected > 100 * 1024**3
            or projected_free * 5 < capacity.usable_bytes
        ):
            raise ArtifactCapacityError("The installation has no safe artifact capacity.")
        ledger.spool_reserved_bytes += limit_bytes
        ledger.protected_reserved_bytes = projected
        attempt = ArtifactAttemptRow(
            id=attempt_id.value,
            artifact_id=artifact_id.value,
            installation_id=scope.installation_id.value,
            organization_id=scope.organization_id.value,
            project_id=scope.project_id.value,
        )
        attempt.created_at = now
        reservation = ArtifactStagingReservationRow(
            id=reservation_id.value,
            attempt_id=attempt_id.value,
            limit_bytes=limit_bytes,
            local_reserved_bytes=limit_bytes,
            remote_reserved_bytes=limit_bytes,
            expires_at=now + timedelta(seconds=transfer_seconds),
        )
        self._session.add(attempt)
        await self._session.flush()
        self._session.add(reservation)
        await self._session.flush()
        return PostgresArtifactAttemptMapper.reservation(attempt, reservation, now)
