from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.infrastructure.types.enum_types import PRINCIPAL_KIND_TYPE
from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class CollectionActionGrantRow(SharedPersistenceBase):
    """Bind one exact Collection action to a current Project membership."""

    __tablename__ = "collection_action_grants"

    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    collection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    recipient_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    action: Mapped[str] = mapped_column(String(100), primary_key=True)
    recipient_kind: Mapped[PrincipalKind] = mapped_column(PRINCIPAL_KIND_TYPE)
    can_grant: Mapped[bool] = mapped_column(Boolean)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
    assigned_by_principal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
