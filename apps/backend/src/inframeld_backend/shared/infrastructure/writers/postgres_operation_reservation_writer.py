"""Reserve operation identities using the caller's PostgreSQL transaction."""

from datetime import datetime, timedelta
from hmac import compare_digest
from typing import final, override
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from inframeld_backend.shared.application.dtos.operation_reservation_request_dto import (
    OperationReservationRequestDTO,
)
from inframeld_backend.shared.application.dtos.operation_reservation_result_dto import (
    OperationReservationResultDTO,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.application.errors.application_errors import (
    ConflictError,
    IdempotencyKeyReusedError,
)
from inframeld_backend.shared.application.protocols.operation_reservation_writer import (
    OperationReservationWriter,
)
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)

_COMPLETED_RETENTION = timedelta(hours=24)


@final
class PostgresOperationReservationWriter(OperationReservationWriter):
    """Reserve once without committing the caller's transaction"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @override
    async def mark_replayable(
        self,
        operation_id: OperationId,
        replay_kind: OperationReplayKind,
    ) -> datetime | None:
        expires_at = (
            None
            if replay_kind is OperationReplayKind.ASYNC_JOB
            else func.clock_timestamp() + _COMPLETED_RETENTION
        )

        statement = (
            update(IdempotencyReservationRow)
            .where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
            )
            .values(
                state=OperationReservationState.REPLAYABLE,
                replay_kind=replay_kind,
                expires_at=expires_at,
            )
            .returning(
                IdempotencyReservationRow.operation_id,
                IdempotencyReservationRow.expires_at,
            )
        )

        updated = (await self._session.execute(statement)).tuples().one_or_none()
        if updated is None:
            raise ConflictError()

        _, stored_expiry = updated
        return stored_expiry

    async def mark_recovery_required(self, operation_id: OperationId) -> None:
        """Record uncertainty only before a safe replay outcome exists."""

        statement = (
            update(IdempotencyReservationRow)
            .where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
            )
            .values(state=OperationReservationState.RECOVERY_REQUIRED, replay_kind=None)
            .returning(IdempotencyReservationRow.operation_id)
        )

        updated_id = (await self._session.execute(statement)).scalar_one_or_none()

        if updated_id is None:
            raise ConflictError

    @override
    async def reserve(
        self, request: OperationReservationRequestDTO
    ) -> OperationReservationResultDTO:
        """Find the original operation or claim a new one in the caller's transaction.

        The scoped unique constraint settles concurrent requests. Only completed
        history past its retention deadline can be replaced.
        """
        project_id = request.project_id.value if request.project_id is not None else None

        # 1. Release this exact key only if its completed outcome has expired.
        # Active and recovery-required operations have no expiry and stay reserved.
        await self._session.execute(
            delete(IdempotencyReservationRow).where(
                IdempotencyReservationRow.principal_id == request.principal_id.value,
                IdempotencyReservationRow.organization_id == request.organization_id.value,
                IdempotencyReservationRow.project_id.is_not_distinct_from(project_id),
                IdempotencyReservationRow.method == request.method,
                IdempotencyReservationRow.requested_route == request.requested_route,
                IdempotencyReservationRow.request_key == request.key.value,
                IdempotencyReservationRow.state == OperationReservationState.REPLAYABLE,
                IdempotencyReservationRow.expires_at <= func.clock_timestamp(),
            )
        )

        # 2. Try to claim the key. A competing request may win the unique
        # constraint, in which case PostgreSQL inserts nothing here.
        candidate_id = OperationId(str(uuid4()))
        statement = (
            insert(IdempotencyReservationRow)
            .values(
                operation_id=candidate_id.value,
                principal_id=request.principal_id.value,
                organization_id=request.organization_id.value,
                project_id=project_id,
                method=request.method,
                requested_route=request.requested_route,
                request_key=request.key.value,
                request_fingerprint=request.fingerprint,
                expires_at=None,
            )
            .on_conflict_do_nothing(constraint="uq_idempotency_reservations_scope")
            .returning(
                IdempotencyReservationRow.operation_id,
                IdempotencyReservationRow.state,
                IdempotencyReservationRow.replay_kind,
            )
        )

        inserted = (await self._session.execute(statement)).tuples().one_or_none()
        if inserted is not None:
            operation_id, state, replay_kind = inserted
            return OperationReservationResultDTO(
                operation_id=OperationId(operation_id),
                created=True,
                state=state,
                replay_kind=replay_kind,
                expires_at=None,
            )

        # 3. If another request won, read its committed operation and decision.
        # That result may be replayed only when the request meaning matches.
        existing_result = await self._session.execute(
            select(
                IdempotencyReservationRow.operation_id,
                IdempotencyReservationRow.request_fingerprint,
                IdempotencyReservationRow.state,
                IdempotencyReservationRow.replay_kind,
                IdempotencyReservationRow.expires_at,
            ).where(
                IdempotencyReservationRow.principal_id == request.principal_id.value,
                IdempotencyReservationRow.organization_id == request.organization_id.value,
                IdempotencyReservationRow.project_id.is_not_distinct_from(project_id),
                IdempotencyReservationRow.method == request.method,
                IdempotencyReservationRow.requested_route == request.requested_route,
                IdempotencyReservationRow.request_key == request.key.value,
            )
        )
        existing = existing_result.tuples().one_or_none()

        if existing is None:
            raise RuntimeError("Conflicting operation reservation was not found after insert.")

        operation_id, saved_fingerprint, state, replay_kind, expires_at = existing
        # The key alone is insufficient: changed input must not inherit the
        # first request's operation, even when its scope and route match.
        if not compare_digest(saved_fingerprint, request.fingerprint):
            raise IdempotencyKeyReusedError()

        # An equivalent retry keeps the original identity and recorded state.
        return OperationReservationResultDTO(
            operation_id=OperationId(operation_id),
            created=False,
            state=state,
            replay_kind=replay_kind,
            expires_at=expires_at,
        )
