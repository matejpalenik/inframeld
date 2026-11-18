from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class CollectionRevisionRow(SharedPersistenceBase):
    """Retain the original scoped operation and reviewed selection base."""

    __tablename__ = "collection_revisions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    collection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    operation_id: Mapped[str] = mapped_column(Text)
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    base_revision_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
