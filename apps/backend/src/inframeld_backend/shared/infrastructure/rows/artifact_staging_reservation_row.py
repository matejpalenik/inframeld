from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ArtifactStagingReservationRow(SharedPersistenceBase):
    __tablename__ = "artifact_staging_reservations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    local_reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remote_reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    staging_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
