from uuid import UUID

from sqlalchemy import BigInteger, LargeBinary, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class StrandedAuthorityRepairReceiptRow(AccessPersistenceBase):
    """Retain typed historical responsibility IDs without coupling to mutable targets."""

    __tablename__ = "stranded_authority_repair_receipts"
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operator_request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    recipient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    expected_identity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    before_revision: Mapped[int] = mapped_column(BigInteger)
    after_revision: Mapped[int] = mapped_column(BigInteger)
    responsibility_kind: Mapped[str] = mapped_column(String(32))
    target_kind: Mapped[str] = mapped_column(String(32))
    project_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    access_group_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    application_account_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    action_id: Mapped[str | None] = mapped_column(String(100))
    model_connection_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
