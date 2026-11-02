from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ArtifactCleanupObligationRow(SharedPersistenceBase):
    __tablename__ = "artifact_cleanup_obligations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    origin_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    transfer_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    origin_operation_id: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    origin_attempt_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    retirement_authorized: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    physically_complete: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    execution_status: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    execution_reason: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)

    staging_reservation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, unique=True, default=None
    )
