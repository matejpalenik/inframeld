from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DurableJobAttemptRow(SharedPersistenceBase):
    """Retain each bounded attempt after replacement or process restart."""

    __tablename__ = "durable_job_attempts"

    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    number: Mapped[int] = mapped_column(Integer, primary_key=True)
    fence: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    worker_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    reason: Mapped[str | None] = mapped_column(String(100), nullable=True, default=None)
