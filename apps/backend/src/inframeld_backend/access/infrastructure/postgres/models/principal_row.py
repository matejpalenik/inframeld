"""Map a human or application principal stored in PostgreSQL."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.principal import PrincipalKind, PrincipalStatus
from inframeld_backend.access.infrastructure.postgres.models.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.postgres.models.enum_types import (
    PRINCIPAL_KIND_TYPE,
    PRINCIPAL_STATUS_TYPE,
)


class PrincipalRow(AccessPersistenceBase):
    """Map a human or application principal stored in PostgreSQL."""

    __tablename__ = "principals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[PrincipalKind] = mapped_column(PRINCIPAL_KIND_TYPE, nullable=False)
    status: Mapped[PrincipalStatus] = mapped_column(PRINCIPAL_STATUS_TYPE, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        init=False,
        server_default=func.now(),
    )
