"""Map a project-local document access group without loading its members."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.postgres.models.access_persistence_base import (
    AccessPersistenceBase,
)


class AccessGroupRow(AccessPersistenceBase):
    """Map a project-local document access group without loading its members."""

    __tablename__ = "access_groups"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
