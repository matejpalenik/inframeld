from decimal import Decimal
from uuid import UUID

from sqlalchemy import BigInteger, Numeric, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ProjectSpendingPolicyRow(SharedPersistenceBase):
    """Map the Project policy and accounting coordination root, without duplicate balances."""

    __tablename__ = "project_spending_policies"
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    revision: Mapped[int] = mapped_column(BigInteger)
    monthly_limit: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
