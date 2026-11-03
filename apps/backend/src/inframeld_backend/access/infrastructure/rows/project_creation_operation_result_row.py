from uuid import UUID

from sqlalchemy import BigInteger, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ProjectCreationOperationResultRow(AccessPersistenceBase):
    """Keep original creation facts under the reservation's existing replay lifetime."""

    __tablename__ = "project_creation_operation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    creator_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    access_revision: Mapped[int] = mapped_column(BigInteger)
    metadata_revision: Mapped[int] = mapped_column(BigInteger)
    initial_actions: Mapped[list[str]] = mapped_column(JSONB)
