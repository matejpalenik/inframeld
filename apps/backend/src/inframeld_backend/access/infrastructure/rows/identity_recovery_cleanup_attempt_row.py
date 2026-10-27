from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class IdentityRecoveryCleanupAttemptRow(AccessPersistenceBase):
    __tablename__ = "identity_recovery_cleanup_attempts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operation_id: Mapped[str] = mapped_column(Text, nullable=False)
    run_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    worker_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    ownership_token: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    claimed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    terminal_reason: Mapped[str | None] = mapped_column(Text, default=None)
