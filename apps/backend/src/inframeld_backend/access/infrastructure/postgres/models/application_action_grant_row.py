"""Map a human's exact action authority on a project-bound application account."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.principal import PrincipalKind
from inframeld_backend.access.infrastructure.postgres.models.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.postgres.models.enum_types import (
    PRINCIPAL_KIND_TYPE,
)


class ApplicationActionGrantRow(AccessPersistenceBase):
    """Map a human's exact action authority on a project-bound application account."""

    __tablename__ = "application_action_grants"
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    application_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    recipient_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    recipient_kind: Mapped[PrincipalKind] = mapped_column(PRINCIPAL_KIND_TYPE)
    action: Mapped[str] = mapped_column(String(100), primary_key=True)
    can_grant: Mapped[bool] = mapped_column(Boolean)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    assigned_by_principal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
