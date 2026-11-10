import math
from datetime import datetime, timedelta
from typing import override

from sqlalchemy import DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.infrastructure.rows.project_row import ProjectRow
from inframeld_backend.shared.application.dtos.artifact_allocation_dto import ArtifactAllocationDTO
from inframeld_backend.shared.application.dtos.artifact_attempt_dto import ArtifactAttemptDTO
from inframeld_backend.shared.application.dtos.artifact_capacity_dto import ArtifactCapacityDTO
from inframeld_backend.shared.application.dtos.artifact_cleanup_job_binding_dto import (
    ArtifactCleanupJobBindingDTO,
)
from inframeld_backend.shared.application.dtos.artifact_cleanup_target_dto import (
    ArtifactCleanupTargetDTO,
)
from inframeld_backend.shared.application.dtos.artifact_scope_dto import ArtifactScopeDTO
from inframeld_backend.shared.application.dtos.artifact_staging_reservation_dto import (
    ArtifactStagingReservationDTO,
)
from inframeld_backend.shared.application.dtos.verified_artifact_dto import VerifiedArtifactDTO
from inframeld_backend.shared.application.errors.artifact_errors import (
    ArtifactCapacityError,
    ArtifactReservationError,
)
from inframeld_backend.shared.application.protocols.artifact_attempt_repository import (
    ArtifactAttemptRepository,
)
from inframeld_backend.shared.application.value_objects.artifact_attempt_id import ArtifactAttemptId
from inframeld_backend.shared.application.value_objects.artifact_id import ArtifactId
from inframeld_backend.shared.application.value_objects.artifact_staging_reservation_id import (
    ArtifactStagingReservationId,
)
from inframeld_backend.shared.infrastructure.mappers.postgres_artifact_attempt_mapper import (
    PostgresArtifactAttemptMapper,
)
from inframeld_backend.shared.infrastructure.mappers.postgres_job_binding_mapper import (
    PostgresJobBindingMapper,
)
from inframeld_backend.shared.infrastructure.rows.application_job_queue_row import (
    ApplicationJobQueueRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_attempt_row import ArtifactAttemptRow
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_obligation_row import (
    ArtifactCleanupObligationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_cleanup_target_row import (
    ArtifactCleanupTargetRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_staging_reservation_row import (
    ArtifactStagingReservationRow,
)
from inframeld_backend.shared.infrastructure.rows.artifact_storage_capacity_row import (
    ArtifactStorageCapacityRow,
)
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresArtifactAttemptRepository(ArtifactAttemptRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def inspect(self, allocation: ArtifactAllocationDTO) -> ArtifactStagingReservationDTO:
        attempt, reservation = await self._original(allocation)
        return PostgresArtifactAttemptMapper.reservation(attempt, reservation, await self._now())

    @override
    async def seal(self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO) -> None:
        row, reservation = await self._original(allocation)
        await self._writable(row, reservation)
        if (
            (attempt.artifact_id.value, attempt.attempt_id.value, attempt.scope)
            != (row.artifact_id, row.id, allocation.reservation.scope)
            or type(attempt.length) is not int
            or not 0 <= attempt.length <= reservation.limit_bytes
        ):
            raise ArtifactReservationError(
                "The sealed target differs from the original allocation."
            )
        if row.length is not None or row.digest is not None:
            self._require_seal(row, attempt)
            return
        if row.put_pending or row.put_confirmed or row.published:
            raise ArtifactReservationError("The original attempt can no longer be sealed.")
        row.length, row.digest, row.state = attempt.length, attempt.digest.value, "sealed"
        await self._session.flush()

    @override
    async def begin_put(
        self, allocation: ArtifactAllocationDTO, attempt: ArtifactAttemptDTO
    ) -> bool:
        row, reservation = await self._original(allocation)
        await self._writable(row, reservation)
        self._require_seal(row, attempt)
        if row.put_pending or row.put_confirmed:
            return False
        row.put_pending, row.state = True, "put_pending"
        await self._session.flush()
        return True

    @override
    async def confirm_verified(
        self, allocation: ArtifactAllocationDTO, verified: VerifiedArtifactDTO
    ) -> None:
        row, reservation = await self._original(allocation)
        await self._writable(row, reservation)
        self._require_seal(row, verified.attempt)
        if not row.put_pending:
            raise ArtifactReservationError("Verification has no original committed PUT intent.")
        row.put_confirmed = True
        if not row.published:
            row.state = "verified"
        # A matching object does not exclude earlier accepted server work.
        await self._session.flush()

    @override
    async def publish_verified(
        self, allocation: ArtifactAllocationDTO, verified: VerifiedArtifactDTO
    ) -> None:
        row, reservation = await self._original(allocation)
        await self._writable(row, reservation)
        self._require_seal(row, verified.attempt)
        if not row.put_confirmed or row.state not in ("verified", "published"):
            raise ArtifactReservationError(
                "The original artifact has no complete persisted verification."
            )
        row.published, row.state = True, "published"
        await self._session.flush()

    @override
    async def retire_local(
        self, binding: ArtifactCleanupJobBindingDTO, target: ArtifactCleanupTargetDTO
    ) -> bool:
        attempt, reservation, member, obligation = await self._cleanup_target(binding, target)
        if await self._now() < obligation.transfer_deadline:
            raise ArtifactReservationError("The original local transfer allowance is still live.")
        attempt.retired = True
        await self._session.flush()
        if reservation.staging_removed:
            if (
                not member.staging_confirmed_removed
                or reservation.local_reserved_bytes != 0
                or not reservation.released
            ):
                raise ArtifactReservationError("The saved local removal is inconsistent.")
            return False
        return True

    @override
    async def confirm_local_removed(
        self, binding: ArtifactCleanupJobBindingDTO, target: ArtifactCleanupTargetDTO
    ) -> None:
        attempt, reservation, member, _ = await self._cleanup_target(binding, target)
        if not attempt.retired:
            raise ArtifactReservationError("Local removal requires permanent retirement first.")
        ledger = await self._session.scalar(
            select(ArtifactStorageCapacityRow)
            .where(
                ArtifactStorageCapacityRow.installation_id == binding.scope.installation_id.value
            )
            .with_for_update()
        )
        if ledger is None:
            raise ArtifactReservationError("The original capacity ledger is unavailable.")
        amount = reservation.local_reserved_bytes
        if (
            amount < 0
            or ledger.spool_reserved_bytes < amount
            or ledger.protected_reserved_bytes < amount
            or ledger.protected_reserved_bytes - amount < ledger.occupied_bytes
        ):
            raise ArtifactReservationError("The original local byte charge is inconsistent.")
        ledger.spool_reserved_bytes -= amount
        ledger.protected_reserved_bytes -= amount
        reservation.local_reserved_bytes = 0
        reservation.staging_removed = reservation.released = member.staging_confirmed_removed = True
        # Remote charges, unknown PUTs and physical-retirement flags remain untouched.
        await self._session.flush()

    async def _now(self) -> datetime:
        now = await self._session.scalar(
            select(func.clock_timestamp(type_=DateTime(timezone=True)))
        )
        if now is None:
            raise ArtifactReservationError("The original storage clock is unavailable.")
        return now

    async def _original(
        self, allocation: ArtifactAllocationDTO
    ) -> tuple[ArtifactAttemptRow, ArtifactStagingReservationRow]:
        if not self._session.in_transaction():
            raise RuntimeError("Artifact transitions require the caller transaction.")
        obligation = await self._session.scalar(
            select(ArtifactCleanupObligationRow)
            .where(
                ArtifactCleanupObligationRow.id == allocation.cleanup_binding.obligation_id.value
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        original = allocation.reservation
        attempt = await self._session.scalar(
            select(ArtifactAttemptRow)
            .where(ArtifactAttemptRow.id == original.attempt_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        reservation = await self._session.scalar(
            select(ArtifactStagingReservationRow)
            .where(ArtifactStagingReservationRow.id == original.reservation_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        member = await self._session.get(
            ArtifactCleanupTargetRow,
            (allocation.cleanup_binding.obligation_id.value, original.attempt_id.value),
        )
        job_id = await self._session.scalar(
            select(DurableJobRow.id).where(
                DurableJobRow.cleanup_obligation_id
                == allocation.cleanup_binding.obligation_id.value
            )
        )
        if (
            obligation is None
            or attempt is None
            or reservation is None
            or member is None
            or original.scope != allocation.cleanup_binding.scope
            or PostgresJobBindingMapper.cleanup(obligation) != allocation.cleanup_binding
            or job_id != allocation.cleanup_job_id.value
            or obligation.staging_reservation_id != reservation.id
            or obligation.transfer_deadline != reservation.expires_at
            or (
                attempt.artifact_id,
                attempt.installation_id,
                attempt.organization_id,
                attempt.project_id,
                reservation.attempt_id,
                reservation.limit_bytes,
                reservation.expires_at,
            )
            != (
                original.artifact_id.value,
                original.scope.installation_id.value,
                original.scope.organization_id.value,
                original.scope.project_id.value,
                original.attempt_id.value,
                original.limit_bytes,
                original.expires_at,
            )
        ):
            raise ArtifactReservationError("The original artifact allocation changed meaning.")
        return attempt, reservation

    async def _writable(
        self, row: ArtifactAttemptRow, reservation: ArtifactStagingReservationRow
    ) -> None:
        if row.retired or reservation.released or reservation.expires_at <= await self._now():
            raise ArtifactReservationError("The original storage attempt is retired or expired.")

    @staticmethod
    def _require_seal(row: ArtifactAttemptRow, attempt: ArtifactAttemptDTO) -> None:
        if (
            row.id,
            row.artifact_id,
            row.installation_id,
            row.organization_id,
            row.project_id,
            row.length,
            row.digest,
        ) != (
            attempt.attempt_id.value,
            attempt.artifact_id.value,
            attempt.scope.installation_id.value,
            attempt.scope.organization_id.value,
            attempt.scope.project_id.value,
            attempt.length,
            attempt.digest.value,
        ):
            raise ArtifactReservationError("The original immutable seal changed.")

    async def _cleanup_target(
        self, binding: ArtifactCleanupJobBindingDTO, target: ArtifactCleanupTargetDTO
    ) -> tuple[
        ArtifactAttemptRow,
        ArtifactStagingReservationRow,
        ArtifactCleanupTargetRow,
        ArtifactCleanupObligationRow,
    ]:
        if not self._session.in_transaction():
            raise RuntimeError("Local settlement requires the caller transaction.")
        obligation = await self._session.scalar(
            select(ArtifactCleanupObligationRow)
            .where(ArtifactCleanupObligationRow.id == binding.obligation_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        member = await self._session.get(
            ArtifactCleanupTargetRow,
            (binding.obligation_id.value, target.attempt_id.value),
            populate_existing=True,
        )
        attempt = await self._session.scalar(
            select(ArtifactAttemptRow)
            .where(ArtifactAttemptRow.id == target.attempt_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        reservation = await self._session.scalar(
            select(ArtifactStagingReservationRow)
            .where(ArtifactStagingReservationRow.attempt_id == target.attempt_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if (
            obligation is None
            or member is None
            or attempt is None
            or reservation is None
            or PostgresJobBindingMapper.cleanup(obligation) != binding
            or target.scope != binding.scope
            or obligation.staging_reservation_id != reservation.id
            or (
                attempt.artifact_id,
                attempt.installation_id,
                attempt.organization_id,
                attempt.project_id,
                attempt.length,
                attempt.digest,
            )
            != (
                target.artifact_id.value,
                target.scope.installation_id.value,
                target.scope.organization_id.value,
                target.scope.project_id.value,
                target.length,
                target.digest.value if target.digest is not None else None,
            )
            or attempt.published
            or attempt.retention_protected
        ):
            raise ArtifactReservationError(
                "The original local cleanup target changed or is protected."
            )
        return attempt, reservation, member, obligation

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
        capacity: ArtifactCapacityDTO,
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

        ledger = await self._session.scalar(
            select(ArtifactStorageCapacityRow)
            .where(ArtifactStorageCapacityRow.installation_id == scope.installation_id.value)
            .with_for_update()
        )
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
