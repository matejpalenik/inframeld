from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, LargeBinary, String, Text, Uuid, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ApplicationKeyRow(AccessPersistenceBase):
    """Store an incoming credential separately from its safe read projection."""

    __tablename__ = "application_keys"
    key_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    application_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    audience: Mapped[str] = mapped_column(Text)
    allowed_adapters: Mapped[list[str]] = mapped_column(ARRAY(String(8)))
    verifier: Mapped[bytes] = mapped_column(LargeBinary, repr=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    issued_by_principal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
