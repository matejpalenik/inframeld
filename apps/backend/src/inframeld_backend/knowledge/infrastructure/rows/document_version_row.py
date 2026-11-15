from uuid import UUID

from sqlalchemy import BigInteger, LargeBinary, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DocumentVersionRow(SharedPersistenceBase):
    __tablename__ = "document_versions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    filename: Mapped[str] = mapped_column(Text, repr=False)
    media_type: Mapped[str] = mapped_column(Text)
    length: Mapped[int] = mapped_column(BigInteger)
    digest: Mapped[bytes] = mapped_column(LargeBinary, repr=False)
