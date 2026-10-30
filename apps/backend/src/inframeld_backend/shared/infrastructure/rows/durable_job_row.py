from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DurableJobRow(SharedPersistenceBase):
    """Persist original admission and the single current ordinary-job fence."""

    __tablename__ = "durable_jobs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operation_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    action_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_kind: Mapped[str] = mapped_column(String(100), nullable=False)
    payload_version: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    queued_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    human_authority: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    human_subject: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    human_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    work_deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    fence: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, default=None)
    worker_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False, default=b"")
    pending_effect: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
    terminal_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
