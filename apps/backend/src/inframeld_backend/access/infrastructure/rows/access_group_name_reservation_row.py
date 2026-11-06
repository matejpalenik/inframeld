from uuid import UUID

from sqlalchemy import Boolean, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class AccessGroupNameReservationRow(AccessPersistenceBase):
    """Keep a Project-scoped Name bound to its original group after deletion."""

    __tablename__ = "access_group_name_reservations"
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    retired: Mapped[bool] = mapped_column(Boolean, default=False)
