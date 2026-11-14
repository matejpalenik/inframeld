from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ModelConnectionCredentialResultRow(AccessPersistenceBase):
    """Retain only the original safe outcome with the ordinary request reservation."""

    __tablename__ = "model_connection_credential_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    model_connection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    credential_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True))
    revision: Mapped[int] = mapped_column(BigInteger)
    present: Mapped[bool] = mapped_column(Boolean)
    changed: Mapped[bool] = mapped_column(Boolean)
    credential_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
