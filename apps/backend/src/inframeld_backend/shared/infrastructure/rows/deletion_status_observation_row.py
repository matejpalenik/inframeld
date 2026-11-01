from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DeletionStatusObservationRow(SharedPersistenceBase):
    """Map optional owner observations without claiming their source proof is implemented."""

    __tablename__ = "deletion_status_observations"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    owner_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner_observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, init=False, server_default=func.clock_timestamp()
    )
    job_status: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    admission_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    access_blocked: Mapped[bool | None] = mapped_column(Boolean, nullable=True, default=None)
    application_shutdown_complete: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    physical_cleanup_complete: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True, default=None
    )
    unfinished_obligation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    unfinished_operation_id: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    unfinished_installation_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    unfinished_organization_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    unfinished_project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    unfinished_initiator_principal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    unfinished_observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    unfinished_source_revision: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    retention_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
