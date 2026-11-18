from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class RetainedHistoryReservationRow(SharedPersistenceBase):
    """Retain an original charge independently of its retry lookup lifetime."""

    __tablename__ = "retained_history_reservations"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, init=False, server_default=func.now()
    )
