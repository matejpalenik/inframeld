from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Numeric, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ProjectSpendingPolicyOperationResultRow(SharedPersistenceBase):
    """Retain the original safe policy outcome under existing replay metadata retention."""

    __tablename__ = "project_spending_policy_operation_results"
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    revision: Mapped[int] = mapped_column(BigInteger)
    monthly_limit: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    changed: Mapped[bool] = mapped_column(Boolean)
