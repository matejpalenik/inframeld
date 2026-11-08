from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, LargeBinary, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class InvitationRow(AccessPersistenceBase):
    """Retain digest-only invitation intent beyond the issuing reservation's lifetime."""

    __tablename__ = "invitations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    issuer_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    token_digest: Mapped[bytes] = mapped_column(LargeBinary)
    assignments: Mapped[list[dict[str, object]]] = mapped_column(JSONB)
    issued_operation_id: Mapped[str] = mapped_column(Text)
    issued_access_revision: Mapped[int] = mapped_column(BigInteger)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    consumed_by_principal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
