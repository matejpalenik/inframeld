from uuid import UUID

from sqlalchemy import BigInteger, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ProjectMetadataOperationResultRow(AccessPersistenceBase):
    """Keep original metadata under the reservation's existing scoped replay lifetime."""

    __tablename__ = "project_metadata_operation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str | None] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    metadata_revision: Mapped[int] = mapped_column(BigInteger)
