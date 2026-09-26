"""Map a verified identity to its local human principal."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.principal import PrincipalKind
from inframeld_backend.access.infrastructure.postgres.models.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.postgres.models.enum_types import (
    PRINCIPAL_KIND_TYPE,
)


class HumanIdentityLinkRow(AccessPersistenceBase):
    """Map a verified identity to its local human principal."""

    __tablename__ = "human_identity_links"

    authority: Mapped[str] = mapped_column(Text, primary_key=True)
    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_kind: Mapped[PrincipalKind] = mapped_column(PRINCIPAL_KIND_TYPE, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        init=False,
        server_default=func.now(),
    )
