from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, LargeBinary, Numeric, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ModelCallAccountingRow(SharedPersistenceBase):
    """Map one call's captured month, immutable basis and current financial state."""

    __tablename__ = "model_call_accounting"
    call_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    operation_id: Mapped[str] = mapped_column(Text)
    meaning_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    period_year: Mapped[int] = mapped_column(BigInteger)
    period_month: Mapped[int] = mapped_column(BigInteger)
    basis: Mapped[dict[str, object] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    reserved_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    hold_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    settled_amount: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    state: Mapped[str] = mapped_column(String(32))
    revision: Mapped[int] = mapped_column(BigInteger)
    reservation_policy_revision: Mapped[int] = mapped_column(BigInteger)
    approved_policy_revision: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
