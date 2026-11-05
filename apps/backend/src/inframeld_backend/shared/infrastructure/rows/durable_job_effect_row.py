from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Integer, LargeBinary, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DurableJobEffectRow(SharedPersistenceBase):
    """Retain one original physical invocation and its non-replayable admission."""

    __tablename__ = "durable_job_effects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    attempt: Mapped[int] = mapped_column(Integer)
    fence: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    unit: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(16))
    binding_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, repr=False)
    artifact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    artifact_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    work_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    checkpoint: Mapped[bytes] = mapped_column(LargeBinary, repr=False)
    length: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    digest: Mapped[bytes | None] = mapped_column(
        LargeBinary, nullable=True, default=None, repr=False
    )
    admitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    aborted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    consumed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
