from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ApplicationJobQueueRow(SharedPersistenceBase):
    """Serialize finite admission and the singleton application execution slot."""

    __tablename__ = "application_job_queue"

    singleton_key: Mapped[int] = mapped_column(Integer, primary_key=True)
