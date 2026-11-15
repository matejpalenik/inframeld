from uuid import UUID

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DocumentGroupRow(SharedPersistenceBase):
    __tablename__ = "document_groups"

    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
