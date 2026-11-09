from uuid import UUID

from sqlalchemy import BigInteger, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ProjectUploadDefaultResultRow(AccessPersistenceBase):
    """Retain private before/after snapshots independently of mutable group rows."""

    __tablename__ = "project_upload_default_results"
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    before_revision: Mapped[int] = mapped_column(BigInteger)
    access_revision: Mapped[int] = mapped_column(BigInteger)
    before_group_ids: Mapped[list[UUID] | None] = mapped_column(ARRAY(Uuid(as_uuid=True)))
    group_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid(as_uuid=True)))
