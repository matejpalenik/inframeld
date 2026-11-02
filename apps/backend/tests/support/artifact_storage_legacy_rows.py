"""Map actual pre-0015 job columns for upgrade fixtures without creating a schema."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import DeclarativeBase, Mapped, MappedAsDataclass, mapped_column


class _LegacyJobBase(MappedAsDataclass, DeclarativeBase, kw_only=True, eq=False):
    pass


class LegacyDurableJobRow(_LegacyJobBase):
    __tablename__ = "durable_jobs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operation_id: Mapped[str] = mapped_column(Text)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    principal_kind: Mapped[str] = mapped_column(String(32))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    action_id: Mapped[str] = mapped_column(String(100))
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    queued_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    payload_kind: Mapped[str] = mapped_column(String(100), default="test.progress")
    payload_version: Mapped[int] = mapped_column(Integer, default=1)
    payload: Mapped[bytes] = mapped_column(LargeBinary, default=b"1")
    status: Mapped[str] = mapped_column(String(32), default="queued")
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    human_authority: Mapped[str | None] = mapped_column(Text, default=None)
    human_subject: Mapped[str | None] = mapped_column(Text, default=None)
    human_version: Mapped[int | None] = mapped_column(BigInteger, default=None)
    work_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    fence: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
    worker_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary, default=b"")
    pending_effect: Mapped[str | None] = mapped_column(String(100), default=None)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str | None] = mapped_column(String(100), default=None)
    terminal_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
