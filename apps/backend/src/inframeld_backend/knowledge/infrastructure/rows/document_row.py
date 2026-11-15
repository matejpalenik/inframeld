from uuid import UUID

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DocumentRow(SharedPersistenceBase):
    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
