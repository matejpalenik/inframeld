from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, LargeBinary, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ProjectDeletionObligationRow(SharedPersistenceBase):
    """Retain exact deletion meaning independently of disposable native request history."""

    __tablename__ = "project_deletion_obligations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    operation_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, unique=True)
    initiator_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_key: Mapped[str] = mapped_column(Text, nullable=False)
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    before_access_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    access_revision: Mapped[int] = mapped_column(BigInteger, nullable=False)
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_revision: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    shutdown_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    physical_cleanup_completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
