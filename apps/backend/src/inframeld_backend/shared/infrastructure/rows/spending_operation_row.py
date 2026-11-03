from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class SpendingOperationRow(SharedPersistenceBase):
    """Retain immutable original work attribution and its cumulative limit without replay expiry."""

    __tablename__ = "spending_operations"
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    principal_kind: Mapped[str] = mapped_column(String(32))
    action_id: Mapped[str] = mapped_column(String(100))
    operation_limit: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    human_authority: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_version: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
