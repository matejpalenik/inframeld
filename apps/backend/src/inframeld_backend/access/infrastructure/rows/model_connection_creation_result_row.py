from uuid import UUID

from sqlalchemy import BigInteger, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ModelConnectionCreationResultRow(AccessPersistenceBase):
    """Preserve the initial connection and assignments across later changes."""

    __tablename__ = "model_connection_creation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    creator_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    model_connection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(32))
    base_url: Mapped[str] = mapped_column(Text)
    api_version: Mapped[str | None] = mapped_column(Text)
    authentication: Mapped[str] = mapped_column(String(32))
    before_revision: Mapped[int] = mapped_column(BigInteger)
    project_access_revision: Mapped[int] = mapped_column(BigInteger)
    initial_actions: Mapped[list[str]] = mapped_column(JSONB)
