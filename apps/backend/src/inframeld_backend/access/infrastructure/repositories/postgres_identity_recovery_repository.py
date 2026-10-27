from dataclasses import dataclass
from datetime import datetime
from typing import final, override

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, AsyncSessionTransaction

from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.protocols.identity_recovery_repository import (
    IdentityRecoveryRepository,
)
from inframeld_backend.access.domain.entities.identity_recovery import IdentityRecovery
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority
from inframeld_backend.access.domain.value_objects.identity_recovery_flow_id import (
    IdentityRecoveryFlowId,
)
from inframeld_backend.access.domain.value_objects.identity_subject import IdentitySubject
from inframeld_backend.access.infrastructure.rows.identity_recovery_admission_row import (
    IdentityRecoveryAdmissionRow,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    ResourceNotFoundError,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.domain.value_objects.installation_id import InstallationId


@dataclass(frozen=True, slots=True)
class _RecoverySnapshot:
    installation_id: InstallationId
    authority: IdentityAuthority
    flow_id: IdentityRecoveryFlowId
    subject: IdentitySubject
    kratos_cleanup_state: IdentityRecoveryCleanupState
    hydra_cleanup_state: IdentityRecoveryCleanupState
    released_at: datetime | None


@dataclass(slots=True)
class _TrackedRecovery:
    recovery: IdentityRecovery
    snapshot: _RecoverySnapshot
    operation_id: OperationId
    event_kind: IdentityRecoveryEventKind
    admitted_at: datetime


def _snapshot(recovery: IdentityRecovery) -> _RecoverySnapshot:
    return _RecoverySnapshot(
        installation_id=recovery.installation_id,
        authority=recovery.authority,
        flow_id=recovery.flow_id,
        subject=recovery.subject,
        kratos_cleanup_state=recovery.kratos_cleanup_state,
        hydra_cleanup_state=recovery.hydra_cleanup_state,
        released_at=recovery.released_at,
    )


@final
class PostgresIdentityRecoveryRepository(IdentityRecoveryRepository):
    """Compare loaded values in a conditional PostgreSQL update to prevent lost progress.

    Keep snapshots on one session transaction. Original admission metadata stays
    in infrastructure, outside the domain checklist. Acquire no explicit locks.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._transaction: AsyncSessionTransaction | None = None
        self._failed = False
        self._tracked: dict[
            tuple[InstallationId, IdentityAuthority, IdentityRecoveryFlowId], _TrackedRecovery
        ] = {}

    def _require_transaction(self) -> None:
        if self._failed:
            raise RuntimeError("This repository cannot be reused after a failed save.")
        transaction = self._session.get_nested_transaction() or self._session.get_transaction()
        if transaction is None or not transaction.is_active:
            raise RuntimeError("An active transaction is required for recovery persistence.")
        if self._transaction is None:
            self._transaction = transaction
        elif transaction is not self._transaction:
            raise RuntimeError("This repository belongs to another transaction.")

    @override
    async def get(
        self,
        *,
        installation_id: InstallationId,
        authority: IdentityAuthority,
        flow_id: IdentityRecoveryFlowId,
    ) -> IdentityRecovery:
        self._require_transaction()
        key = (installation_id, authority, flow_id)
        tracked = self._tracked.get(key)
        if tracked is not None:
            return tracked.recovery

        statement = select(
            IdentityRecoveryAdmissionRow.operation_id,
            IdentityRecoveryAdmissionRow.installation_id,
            IdentityRecoveryAdmissionRow.authority,
            IdentityRecoveryAdmissionRow.flow_id,
            IdentityRecoveryAdmissionRow.subject,
            IdentityRecoveryAdmissionRow.event_kind,
            IdentityRecoveryAdmissionRow.admitted_at,
            IdentityRecoveryAdmissionRow.kratos_cleanup_state,
            IdentityRecoveryAdmissionRow.hydra_cleanup_state,
            IdentityRecoveryAdmissionRow.released_at,
        ).where(
            IdentityRecoveryAdmissionRow.installation_id == installation_id.value,
            IdentityRecoveryAdmissionRow.authority == authority.value,
            IdentityRecoveryAdmissionRow.flow_id == flow_id.value,
        )
        row = (await self._session.execute(statement)).one_or_none()
        if row is None:
            raise ResourceNotFoundError()
        (
            operation_id,
            stored_installation,
            stored_authority,
            stored_flow,
            subject,
            event_kind,
            admitted_at,
            kratos_state,
            hydra_state,
            released_at,
        ) = row
        recovery = IdentityRecovery(
            installation_id=InstallationId(stored_installation),
            authority=IdentityAuthority(stored_authority),
            flow_id=IdentityRecoveryFlowId(stored_flow),
            subject=IdentitySubject(subject),
            kratos_cleanup_state=kratos_state,
            hydra_cleanup_state=hydra_state,
            released_at=released_at,
        )
        self._tracked[key] = _TrackedRecovery(
            recovery=recovery,
            snapshot=_snapshot(recovery),
            operation_id=OperationId(operation_id),
            event_kind=event_kind,
            admitted_at=admitted_at,
        )
        return recovery

    @override
    async def save(self, recovery: IdentityRecovery) -> None:
        try:
            self._require_transaction()
            tracked = self._tracked.get(recovery.identity)
            if tracked is None or tracked.recovery is not recovery:
                raise RuntimeError("Save only the recovery instance loaded by this repository.")
            original = tracked.snapshot
            current = _snapshot(recovery)
            if (
                current.installation_id != original.installation_id
                or current.authority != original.authority
                or current.flow_id != original.flow_id
                or current.subject != original.subject
            ):
                raise RuntimeError("The recovery identity binding cannot be modified.")
            if current == original:
                return

            statement = (
                update(IdentityRecoveryAdmissionRow)
                .where(
                    IdentityRecoveryAdmissionRow.operation_id == tracked.operation_id.value,
                    IdentityRecoveryAdmissionRow.installation_id == original.installation_id.value,
                    IdentityRecoveryAdmissionRow.authority == original.authority.value,
                    IdentityRecoveryAdmissionRow.flow_id == original.flow_id.value,
                    IdentityRecoveryAdmissionRow.subject == original.subject.value,
                    IdentityRecoveryAdmissionRow.event_kind == tracked.event_kind,
                    IdentityRecoveryAdmissionRow.admitted_at == tracked.admitted_at,
                    IdentityRecoveryAdmissionRow.kratos_cleanup_state
                    == original.kratos_cleanup_state,
                    IdentityRecoveryAdmissionRow.hydra_cleanup_state
                    == original.hydra_cleanup_state,
                    IdentityRecoveryAdmissionRow.released_at.is_not_distinct_from(
                        original.released_at
                    ),
                )
                .values(
                    kratos_cleanup_state=current.kratos_cleanup_state,
                    hydra_cleanup_state=current.hydra_cleanup_state,
                    released_at=current.released_at,
                )
                .returning(IdentityRecoveryAdmissionRow.operation_id)
            )
            if (await self._session.execute(statement)).scalar_one_or_none() is None:
                raise ConflictError("The recovery admission or cleanup state has changed.")
            tracked.snapshot = current
        except BaseException:
            # Cancellation invalidates snapshots too. The transaction owner rolls back.
            self._failed = True
            raise
