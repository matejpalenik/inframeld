from sqlalchemy import BigInteger, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class RetainedHistoryCapacityRow(SharedPersistenceBase):
    """Serialize ordinary retained-history charges for the installation."""

    __tablename__ = "retained_history_capacity"

    singleton_key: Mapped[int] = mapped_column(SmallInteger, primary_key=True, autoincrement=False)
    ordinary_limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reserved_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
