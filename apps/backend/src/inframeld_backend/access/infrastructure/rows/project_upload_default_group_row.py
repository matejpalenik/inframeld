from uuid import UUID

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ProjectUploadDefaultGroupRow(AccessPersistenceBase):
    """Map each real saved group link. Alembic owns scoped restrictive constraints."""

    __tablename__ = "project_upload_default_groups"
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
