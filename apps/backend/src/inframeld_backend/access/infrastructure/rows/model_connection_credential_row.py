from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, LargeBinary, SmallInteger, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ModelConnectionCredentialRow(AccessPersistenceBase):
    """Keep the stable slot and last revision even after the stored secret is removed."""

    __tablename__ = "model_connection_credentials"

    credential_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    model_connection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    revision: Mapped[int] = mapped_column(BigInteger)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    format_version: Mapped[int | None] = mapped_column(SmallInteger)
    algorithm: Mapped[str | None] = mapped_column(String(32))
    key_id: Mapped[str | None] = mapped_column(String(64))
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary, repr=False)
