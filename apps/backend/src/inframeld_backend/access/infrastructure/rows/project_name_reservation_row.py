from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class ProjectNameReservationRow(AccessPersistenceBase):
    """Retain exact allocation history so a retired name cannot identify another Project."""

    __tablename__ = "project_name_reservations"

    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    binding_revision: Mapped[int] = mapped_column(BigInteger)
    retired: Mapped[bool] = mapped_column(Boolean)
