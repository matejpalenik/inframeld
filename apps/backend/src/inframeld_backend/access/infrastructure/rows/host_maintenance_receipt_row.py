from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class HostMaintenanceReceiptRow(AccessPersistenceBase):
    """Keep the original accepted operator authorization and its replayable result."""

    __tablename__ = "host_maintenance_receipts"

    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operator_request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    authority: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)
    recovery_operation_id: Mapped[str | None] = mapped_column(Text)
    operator_label: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    outcome: Mapped[str] = mapped_column(Text)
    released: Mapped[bool | None] = mapped_column(Boolean)
    run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspension_obligation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
    suspension_repeat_step: Mapped[str | None] = mapped_column(Text, default=None)
    suspension_repeat_attempt: Mapped[int | None] = mapped_column(Integer, default=None)
    suspension_repeat_fence: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
    suspension_repeat_consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
