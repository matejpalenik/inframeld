from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, SmallInteger, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class InstallationIdentityRow(SharedPersistenceBase):
    """Map the single installation identity initialized by Alembic."""

    __tablename__ = "installation_identity"

    # singleton_key is always 1. The migration will enforce that value, so the table can contain at most one identity.
    singleton_key: Mapped[int] = mapped_column(
        SmallInteger,
        primary_key=True,
        autoincrement=False,
        init=False,
        default=1,
    )
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        init=False,
        server_default=func.now(),
    )
