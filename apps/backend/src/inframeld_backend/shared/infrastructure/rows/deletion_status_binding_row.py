from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, LargeBinary, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DeletionStatusBindingRow(SharedPersistenceBase):
    """Retain original correlation without foreign keys to disposable product records."""

    __tablename__ = "deletion_status_bindings"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    initiator_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    method: Mapped[str] = mapped_column(String(16), nullable=False)
    requested_route: Mapped[str] = mapped_column(Text, nullable=False)
    request_key: Mapped[str] = mapped_column(String(128), nullable=False)
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    authority_family: Mapped[str] = mapped_column(String(32), nullable=False)
    action_id: Mapped[str] = mapped_column(String(100), nullable=False)
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    retention_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, init=False, server_default=func.clock_timestamp()
    )
