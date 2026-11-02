from uuid import UUID

from sqlalchemy import BigInteger, LargeBinary, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class FirstAdministratorBootstrapReceiptRow(AccessPersistenceBase):
    """Retain the one installation claim independently of its current grants."""

    __tablename__ = "first_administrator_bootstrap_receipts"

    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operator_request_id: Mapped[str] = mapped_column(Text)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_name: Mapped[str] = mapped_column(Text)
    recipient_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    expected_identity_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    before_revision: Mapped[int] = mapped_column(BigInteger)
    after_revision: Mapped[int] = mapped_column(BigInteger)
