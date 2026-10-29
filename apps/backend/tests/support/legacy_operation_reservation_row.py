"""Seed pre-lookup reservations while qualifying the additive migration."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class _LegacyBase(MappedAsDataclass, DeclarativeBase, kw_only=True):
    pass


class LegacyOperationReservationRow(_LegacyBase):
    """Map only columns present at migration 0008, without current insert defaults."""

    __tablename__ = "idempotency_reservations"
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    method: Mapped[str] = mapped_column(String(16))
    requested_route: Mapped[str] = mapped_column(Text)
    request_key: Mapped[str] = mapped_column(String(128))
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    state: Mapped[str] = mapped_column(String(32))
    replay_kind: Mapped[str | None] = mapped_column(String(32))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
