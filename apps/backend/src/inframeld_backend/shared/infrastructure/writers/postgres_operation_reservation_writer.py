"""Reserve operation identities using the caller's PostgreSQL transaction."""

from hmac import compare_digest
from typing import final
from uuid import uuid4

from sqlalchemy import select, update
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
from inframeld_backend.shared.application.value_objects.operation_id import OperationId
from inframeld_backend.shared.infrastructure.rows.idempotency_reservation_row import (
    IdempotencyReservationRow,
)


@final
class PostgresOperationReservationWriter:
    """Reserve once without committing the caller's transaction"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def mark_replayable(
        self,
        operation_id: OperationId,
        replay_kind: OperationReplayKind,
    ) -> None:
        statement = (
            update(IdempotencyReservationRow)
            .where(
                IdempotencyReservationRow.operation_id == operation_id.value,
                IdempotencyReservationRow.state == OperationReservationState.IN_PROGRESS,
            )
            .values(state=OperationReservationState.REPLAYABLE, replay_kind=replay_kind)
            .returning(IdempotencyReservationRow.operation_id)
        )

        updated_id = (await self._session.execute(statement)).scalar_one_or_none()

        if updated_id is None:
            raise ConflictError

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

    async def reserve(
        self, request: OperationReservationRequestDTO
    ) -> OperationReservationResultDTO:
        """Return the original operation for an equal request; reject changed input."""
        candidate_id = OperationId(str(uuid4()))
        project_id = request.project_id.value if request.project_id is not None else None

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
            )

        existing = await self._session.execute(
            select(
                IdempotencyReservationRow.operation_id,
                IdempotencyReservationRow.request_fingerprint,
                IdempotencyReservationRow.state,
                IdempotencyReservationRow.replay_kind,
            ).where(
                IdempotencyReservationRow.principal_id == request.principal_id.value,
                IdempotencyReservationRow.organization_id == request.organization_id.value,
                IdempotencyReservationRow.project_id.is_not_distinct_from(project_id),
                IdempotencyReservationRow.method == request.method,
                IdempotencyReservationRow.requested_route == request.requested_route,
                IdempotencyReservationRow.request_key == request.key.value,
            )
        )

        operation_id, saved_fingerprint, state, replay_kind = existing.tuples().one()

        if not compare_digest(saved_fingerprint, request.fingerprint):
            raise IdempotencyKeyReusedError

        return OperationReservationResultDTO(
            operation_id=OperationId(operation_id),
            created=False,
            state=state,
            replay_kind=replay_kind,
        )
