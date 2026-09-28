from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class GroupMembershipRow(AccessPersistenceBase):
    """Map ordinary group membership, independently of management and action grants."""

    __tablename__ = "group_memberships"
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    assigned_by_principal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
