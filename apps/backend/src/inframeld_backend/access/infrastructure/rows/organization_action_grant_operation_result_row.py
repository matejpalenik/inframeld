from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class OrganizationActionGrantOperationResultRow(AccessPersistenceBase):
    """Retain the original Organization transition independently of its current grant."""

    __tablename__ = "organization_action_grant_operation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    recipient_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    action_id: Mapped[str] = mapped_column(String(100))
    method: Mapped[str] = mapped_column(String(6))
    before_revision: Mapped[int] = mapped_column(BigInteger)
    access_revision: Mapped[int] = mapped_column(BigInteger)
    before_can_grant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    can_grant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    changed: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int] = mapped_column(Integer)
