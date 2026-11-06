from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class AccessGroupRelationshipResultRow(AccessPersistenceBase):
    """Retain the exact original transition after later departures or rejoining."""

    __tablename__ = "access_group_relationship_results"
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    before_revision: Mapped[int] = mapped_column(BigInteger)
    access_revision: Mapped[int] = mapped_column(BigInteger)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    change_kind: Mapped[str] = mapped_column(String(32))
    before_member: Mapped[bool] = mapped_column(Boolean)
    before_manager: Mapped[bool] = mapped_column(Boolean)
    member: Mapped[bool] = mapped_column(Boolean)
    manager: Mapped[bool] = mapped_column(Boolean)
    changed: Mapped[bool] = mapped_column(Boolean)
    status_code: Mapped[int] = mapped_column(Integer)
