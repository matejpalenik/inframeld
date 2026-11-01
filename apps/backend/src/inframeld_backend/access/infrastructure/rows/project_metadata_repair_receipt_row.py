from uuid import UUID

from sqlalchemy import BigInteger, LargeBinary, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ProjectMetadataRepairReceiptRow(AccessPersistenceBase):
    __tablename__ = "project_metadata_repair_receipts"

    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operator_request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    recipient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    expected_identity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    before_revision: Mapped[int] = mapped_column(BigInteger)
    after_revision: Mapped[int] = mapped_column(BigInteger)
