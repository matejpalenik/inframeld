from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ProjectActionGrantOperationResultRow(AccessPersistenceBase):
    """Retain an original grant outcome independently of the current assignment."""

    __tablename__ = "project_action_grant_operation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    recipient_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    action_id: Mapped[str] = mapped_column(String(100))
    change_kind: Mapped[str] = mapped_column(String(16))
    before_revision: Mapped[int] = mapped_column(BigInteger)
    access_revision: Mapped[int] = mapped_column(BigInteger)
    changed: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int] = mapped_column(Integer)
    before_can_grant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    can_grant: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
