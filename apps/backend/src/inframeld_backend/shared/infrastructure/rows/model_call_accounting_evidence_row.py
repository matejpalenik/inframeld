from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ModelCallAccountingEvidenceRow(SharedPersistenceBase):
    """Keep immutable observations, financial application and marker resolution distinct."""

    __tablename__ = "model_call_accounting_evidence"
    call_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    evidence_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(32))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_reference: Mapped[str] = mapped_column(Text)
    usage: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB(none_as_null=True), nullable=True
    )
    charge: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    was_pending: Mapped[bool] = mapped_column(Boolean)
    applied_state: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    applied_hold_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )
    applied_settled_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )
    applied_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    applied_approved_policy_revision: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None
    )
    resolved_by_evidence_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), nullable=True, default=None
    )
    resolution_state: Mapped[str | None] = mapped_column(String(32), nullable=True, default=None)
    resolution_hold_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )
    resolution_settled_amount: Mapped[Decimal | None] = mapped_column(
        Numeric, nullable=True, default=None
    )
    resolution_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True, default=None)
    resolution_approved_policy_revision: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, default=None
    )
