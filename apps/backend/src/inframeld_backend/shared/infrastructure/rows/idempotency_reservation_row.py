from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID

from sqlalchemy import DateTime, LargeBinary, String, Text, Uuid, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.application.enums.operation_replay_kind import (
    OperationReplayKind,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)
from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


def _enum_values(members: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in members]


_STATE_TYPE = SqlEnum(
    OperationReservationState,
    native_enum=False,
    values_callable=_enum_values,
    length=32,
    validate_strings=True,
)

_REPLAY_KIND_TYPE = SqlEnum(
    OperationReplayKind,
    native_enum=False,
    values_callable=_enum_values,
    length=32,
    validate_strings=True,
)


class IdempotencyReservationRow(SharedPersistenceBase):
    """Map the durable identity and replay classification of one request."""

    __tablename__ = "idempotency_reservations"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_route: Mapped[str] = mapped_column(Text, nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    state: Mapped[OperationReservationState] = mapped_column(
        _STATE_TYPE,
        nullable=False,
        init=False,
        server_default=OperationReservationState.IN_PROGRESS.value,
    )
    replay_kind: Mapped[OperationReplayKind | None] = mapped_column(
        _REPLAY_KIND_TYPE,
        nullable=True,
        default=None,
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        init=False,
        server_default=func.now(),
    )
