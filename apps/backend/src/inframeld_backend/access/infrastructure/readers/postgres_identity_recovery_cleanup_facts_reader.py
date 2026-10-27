from typing import override

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.identity_recovery_cleanup_work_dto import (
    IdentityRecoveryCleanupWorkDTO,
)
from inframeld_backend.access.application.dtos.verified_human_identity_dto import (
    VerifiedHumanIdentityDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_facts_reader import (
    IdentityRecoveryCleanupFactsReader,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.mappers.postgres_identity_recovery_cleanup_work_mapper import (
    PostgresIdentityRecoveryCleanupWorkMapper,
)
from inframeld_backend.access.infrastructure.readers.identity_recovery_cleanup_work_queries import (
    IdentityRecoveryCleanupWorkQueries,
)
from inframeld_backend.access.infrastructure.resources.postgres_identity_coordinator import (
    PostgresIdentityCoordinator,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_step_row import (
    IdentityRecoveryCleanupStepRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    DependencyUnavailableError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId
from inframeld_backend.shared.infrastructure.rows.installation_identity_row import (
    InstallationIdentityRow,
)


class PostgresIdentityRecoveryCleanupFactsReader(IdentityRecoveryCleanupFactsReader):
    def __init__(
        self,
        session: AsyncSession,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
    ) -> None:
        self._session = session
        self._installation_id = installation_id
        self._authority = authority

    async def _require_scope(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Cleanup observations require an active transaction.")
        installed = await self._session.scalar(
            select(InstallationIdentityRow.installation_id)
            .where(InstallationIdentityRow.singleton_key == 1)
            .execution_options(autoflush=False)
        )
        if installed != self._installation_id.value:
            raise DependencyUnavailableError("The installation identity is not available.")

    @override
    async def next_candidate(self) -> OperationId | None:
        await self._require_scope()
        result = await self._session.scalar(
            select(IdentityRecoveryCleanupJobRow.operation_id)
            .join(
                IdentityRecoveryCleanupRunRow,
                IdentityRecoveryCleanupRunRow.operation_id
                == IdentityRecoveryCleanupJobRow.operation_id,
            )
            .where(
                IdentityRecoveryCleanupJobRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupJobRow.authority == self._authority.value,
                IdentityRecoveryCleanupRunRow.ended_at.is_(None),
                IdentityRecoveryCleanupRunRow.next_attempt_at <= func.now(),
                or_(
                    IdentityRecoveryCleanupJobRow.lease_expires_at.is_(None),
                    IdentityRecoveryCleanupJobRow.lease_expires_at <= func.now(),
                ),
            )
            .order_by(
                IdentityRecoveryCleanupRunRow.next_attempt_at,
                IdentityRecoveryCleanupJobRow.operation_id,
            )
            .limit(1)
            .execution_options(autoflush=False)
        )
        return None if result is None else OperationId(result)

    @override
    async def lock_work(self, operation_id: OperationId) -> IdentityRecoveryCleanupWorkDTO | None:
        await self._require_scope()
        subject = await self._session.scalar(
            select(IdentityRecoveryCleanupJobRow.subject)
            .where(
                IdentityRecoveryCleanupJobRow.operation_id == operation_id.value,
                IdentityRecoveryCleanupJobRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupJobRow.authority == self._authority.value,
            )
            .execution_options(autoflush=False)
        )
        if subject is None:
            return None

        identity = VerifiedHumanIdentityDTO(self._authority, IdentitySubject(subject))
        await PostgresIdentityCoordinator(self._session).acquire(
            installation_id=self._installation_id, identity=identity
        )
        await self._require_scope()

        statement = IdentityRecoveryCleanupWorkQueries.statement(
            installation_id=self._installation_id, identity=identity, operation_id=operation_id
        )
        result = (await self._session.execute(statement)).one_or_none()
        if result is None:
            return None

        job, run, admission, receipt, version = result
        steps = ()
        if job.active_attempt_id is not None:
            stored_steps = await self._session.scalars(
                select(IdentityRecoveryCleanupStepRow)
                .where(IdentityRecoveryCleanupStepRow.attempt_id == job.active_attempt_id)
                .execution_options(populate_existing=True)
            )
            steps = tuple(
                PostgresIdentityRecoveryCleanupWorkMapper.step(row) for row in stored_steps
            )

        work = PostgresIdentityRecoveryCleanupWorkMapper.from_rows(
            self._installation_id, job, run, admission, receipt, version, steps
        )
        if work.admission.event.identity != identity:
            raise RuntimeError("Cleanup records changed their original identity binding.")
        return work
