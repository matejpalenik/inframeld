from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ApplicationKeyIssuanceResultRow(AccessPersistenceBase):
    """Retain safe original metadata independently of later key lifecycle changes."""

    __tablename__ = "application_key_issuance_results"
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    application_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    issuer_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    key_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    allowed_adapters: Mapped[list[str]] = mapped_column(ARRAY(String(8)))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    before_revision: Mapped[int] = mapped_column(BigInteger)
    access_revision: Mapped[int] = mapped_column(BigInteger)
