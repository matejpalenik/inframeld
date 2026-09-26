"""Map human management appointments whose membership is enforced by PostgreSQL."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.principal import PrincipalKind
from inframeld_backend.access.infrastructure.postgres.models.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.postgres.models.enum_types import (
    PRINCIPAL_KIND_TYPE,
)


class GroupManagerRow(AccessPersistenceBase):
    """Map human management appointments whose membership is enforced by PostgreSQL."""

    __tablename__ = "group_managers"
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    principal_kind: Mapped[PrincipalKind] = mapped_column(PRINCIPAL_KIND_TYPE)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    assigned_by_principal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
