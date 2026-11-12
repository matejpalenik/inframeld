from datetime import datetime

from sqlalchemy import DateTime, String, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.domain.enums.job_status import JobStatus
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.durable_job_row import DurableJobRow
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresRecoveryWorkerSlot:
    """Serialize both cleanup families' claims until the caller commits or rolls back."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def acquire_if_free(self, installation_id: InstallationId) -> datetime | None:
        """Take the installation turn first and observe occupancy after any wait."""
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Recovery claims require an active caller transaction.")

        with self._session.no_autoflush:
            isolation = await self._session.scalar(
                select(func.current_setting("transaction_isolation", type_=String()))
            )
            if isolation != "read committed":
                raise RuntimeError("Recovery claims require READ COMMITTED isolation.")
            # NO KEY UPDATE serializes claims without blocking installation FK checks.
            installed = await self._session.scalar(
                select(InstallationIdentityRow.installation_id)
                .where(InstallationIdentityRow.singleton_key == 1)
                .with_for_update(key_share=True)
            )
            if installed != installation_id.value:
                raise DependencyUnavailableError("The installation identity is not available.")
            now = await self._session.scalar(
                select(func.clock_timestamp(type_=DateTime(timezone=True)))
            )
            if now is None:
                raise DependencyUnavailableError("The authoritative database clock is unavailable.")

            routine = exists().where(
                IdentityRecoveryCleanupJobRow.installation_id == installed,
                IdentityRecoveryCleanupJobRow.lease_expires_at > now,
            )
            suspension = exists().where(
                DurableJobRow.installation_id == installed,
                DurableJobRow.binding_kind == "human_suspension",
                DurableJobRow.status == JobStatus.RUNNING.value,
                DurableJobRow.lease_expires_at > now,
            )
            occupied = await self._session.scalar(select(or_(routine, suspension)))
            if occupied is None:
                raise DependencyUnavailableError("The recovery slot is unavailable.")
            return None if occupied else now
