from uuid import UUID

from sqlalchemy import Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DocumentUploadGroupRow(SharedPersistenceBase):
    __tablename__ = "document_upload_groups"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
