from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ModelConnectionRow(AccessPersistenceBase):
    """Store the current non-secret connection configuration and its exact Project."""

    __tablename__ = "model_connections"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(Text)
    api_version: Mapped[str | None] = mapped_column(Text)
    authentication: Mapped[str] = mapped_column(String(32))
    access_revision: Mapped[int] = mapped_column(BigInteger, init=False, server_default="0")
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
