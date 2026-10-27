from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class IdentityRecoveryCleanupProofRow(AccessPersistenceBase):
    """Keep complete source evidence and independently pending local completion."""

    __tablename__ = "identity_recovery_cleanup_proofs"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authority: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    source_operation_id: Mapped[str] = mapped_column(Text, nullable=False)
    source_receipt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    cli_confirmation_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    login_confirmation_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reconcile_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    propagation_complete: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    release_status: Mapped[str | None] = mapped_column(Text, default=None)
