from datetime import datetime
from typing import override

from sqlalchemy import exists, or_, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.access.application.dtos.identity_recovery_admission_dto import (
    IdentityRecoveryAdmissionDTO,
)
from inframeld_backend.access.application.dtos.identity_recovery_cleanup_proof_dto import (
    IdentityRecoveryCleanupProofDTO,
)
from inframeld_backend.access.application.protocols.identity_recovery_cleanup_proof_writer import (
    IdentityRecoveryCleanupProofWriter,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_attempt_row import (
    IdentityRecoveryCleanupAttemptRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_job_row import (
    IdentityRecoveryCleanupJobRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_proof_row import (
    IdentityRecoveryCleanupProofRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_cleanup_run_row import (
    IdentityRecoveryCleanupRunRow,
)
from inframeld_backend.access.infrastructure.rows.identity_recovery_proof_link_row import (
    IdentityRecoveryProofLinkRow,
)
from inframeld_backend.shared.application.errors.application_errors import ConflictError
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


class PostgresIdentityRecoveryCleanupProofWriter(IdentityRecoveryCleanupProofWriter):
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

    def _require_transaction(self) -> None:
        if not self._session.in_transaction() or not self._session.is_active:
            raise RuntimeError("Cleanup proof persistence requires an active transaction.")

    @override
    async def apply_to_covered(
        self,
        source: IdentityRecoveryCleanupProofDTO,
        target: IdentityRecoveryAdmissionDTO,
        *,
        at: datetime,
    ) -> None:
        self._require_transaction()
        original_source = source.source_admission
        if (
            source.installation_id != self._installation_id
            or original_source.event.identity != target.event.identity
            or target.event.identity.authority != self._authority
        ):
            raise RuntimeError("Cleanup proof changed its identity binding.")

        linked = await self._session.scalar(
            select(
                exists().where(
                    IdentityRecoveryProofLinkRow.installation_id == self._installation_id.value,
                    IdentityRecoveryProofLinkRow.authority == self._authority.value,
                    IdentityRecoveryProofLinkRow.subject == target.event.identity.subject.value,
                    IdentityRecoveryProofLinkRow.covering_operation_id
                    == original_source.operation_id.value,
                    IdentityRecoveryProofLinkRow.covered_operation_id == target.operation_id.value,
                )
            )
        )
        if not linked:
            raise ConflictError("The recovery does not have this original coverage link.")

        await self._session.execute(
            insert(IdentityRecoveryCleanupProofRow)
            .values(
                operation_id=target.operation_id.value,
                installation_id=self._installation_id.value,
                authority=self._authority.value,
                subject=target.event.identity.subject.value,
                source_operation_id=original_source.operation_id.value,
                source_receipt_id=source.source_receipt_id,
                cli_confirmation_attempt_id=source.cli_confirmation_attempt_id,
                login_confirmation_attempt_id=source.login_confirmation_attempt_id,
                recorded_at=at,
                reconcile_at=at,
                propagation_complete=True,
            )
            .on_conflict_do_nothing()
        )

        job = await self._session.scalar(
            select(IdentityRecoveryCleanupJobRow)
            .where(IdentityRecoveryCleanupJobRow.operation_id == target.operation_id.value)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if job is not None:
            await self._session.execute(
                update(IdentityRecoveryCleanupRunRow)
                .where(
                    IdentityRecoveryCleanupRunRow.operation_id == job.operation_id,
                    IdentityRecoveryCleanupRunRow.ended_at.is_(None),
                )
                .values(ended_at=at, terminal_reason="satisfied_by_newer_recovery")
            )
            if job.active_attempt_id is not None:
                await self._session.execute(
                    update(IdentityRecoveryCleanupAttemptRow)
                    .where(
                        IdentityRecoveryCleanupAttemptRow.id == job.active_attempt_id,
                        IdentityRecoveryCleanupAttemptRow.ended_at.is_(None),
                    )
                    .values(ended_at=at, terminal_reason="satisfied_by_newer_recovery")
                )
            job.worker_id = None
            job.ownership_token = None
            job.active_attempt_id = None
            job.lease_expires_at = None
            await self._session.flush()

        await self._session.execute(
            update(IdentityRecoveryProofLinkRow)
            .where(
                IdentityRecoveryProofLinkRow.installation_id == self._installation_id.value,
                IdentityRecoveryProofLinkRow.authority == self._authority.value,
                IdentityRecoveryProofLinkRow.subject == target.event.identity.subject.value,
                IdentityRecoveryProofLinkRow.covering_operation_id
                == original_source.operation_id.value,
                IdentityRecoveryProofLinkRow.covered_operation_id == target.operation_id.value,
                IdentityRecoveryProofLinkRow.reconciled_at.is_(None),
            )
            .values(reconciled_at=at)
        )

    @override
    async def record_checked(
        self, operation_id: OperationId, *, at: datetime, released: bool
    ) -> None:
        self._require_transaction()
        unchecked = IdentityRecoveryCleanupProofRow.checked_at.is_(None)
        permitted = (
            or_(unchecked, IdentityRecoveryCleanupProofRow.release_status == "ineligible")
            if released
            else unchecked
        )
        scope = (
            IdentityRecoveryCleanupProofRow.operation_id == operation_id.value,
            IdentityRecoveryCleanupProofRow.installation_id == self._installation_id.value,
            IdentityRecoveryCleanupProofRow.authority == self._authority.value,
        )
        changed = await self._session.scalar(
            update(IdentityRecoveryCleanupProofRow)
            .where(*scope, permitted)
            .values(checked_at=at, release_status="released" if released else "ineligible")
            .returning(IdentityRecoveryCleanupProofRow.operation_id)
        )
        if (
            changed is None
            and await self._session.scalar(
                select(IdentityRecoveryCleanupProofRow.operation_id).where(*scope)
            )
            is None
        ):
            raise RuntimeError("Completion requires its saved cleanup proof.")

    @override
    async def defer(self, operation_id: OperationId, *, until: datetime) -> None:
        self._require_transaction()
        await self._session.execute(
            update(IdentityRecoveryCleanupProofRow)
            .where(
                IdentityRecoveryCleanupProofRow.operation_id == operation_id.value,
                IdentityRecoveryCleanupProofRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupProofRow.authority == self._authority.value,
            )
            .values(reconcile_at=until)
        )

    @override
    async def mark_propagated(self, operation_id: OperationId) -> None:
        self._require_transaction()
        await self._session.execute(
            update(IdentityRecoveryCleanupProofRow)
            .where(
                IdentityRecoveryCleanupProofRow.operation_id == operation_id.value,
                IdentityRecoveryCleanupProofRow.installation_id == self._installation_id.value,
                IdentityRecoveryCleanupProofRow.authority == self._authority.value,
            )
            .values(propagation_complete=True)
        )
