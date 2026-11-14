from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ModelConnectionGrantResultRow(AccessPersistenceBase):
    """Keep an original grant transition independent of the removable assignment."""

    __tablename__ = "model_connection_grant_operation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    model_connection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    recipient_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    action: Mapped[str] = mapped_column(String(100))
    before_can_grant: Mapped[bool | None] = mapped_column(Boolean)
    can_grant: Mapped[bool | None] = mapped_column(Boolean)
    before_revision: Mapped[int] = mapped_column(BigInteger)
    access_revision: Mapped[int] = mapped_column(BigInteger)
    status_code: Mapped[int] = mapped_column(Integer)
