from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, LargeBinary, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ArtifactAttemptRow(SharedPersistenceBase):
    __tablename__ = "artifact_attempts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    artifact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="allocated")
    length: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    digest: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True, default=None)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retired: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    put_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    put_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retention_protected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, init=False, server_default=func.clock_timestamp()
    )
