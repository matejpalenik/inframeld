from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class AccessAuditEventRow(AccessPersistenceBase):
    """Map the historical record of one Access change."""

    __tablename__ = "access_audit_events"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    actor_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    target_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    target_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        init=False,
        server_default=func.now(),
    )
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, default=None)
    actor_principal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    actor_reference: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    affected_principal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    action: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    before_values: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    after_values: Mapped[dict[str, object] | None] = mapped_column(
        JSONB, nullable=True, default=None
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    correlation_id: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
