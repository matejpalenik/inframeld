from uuid import UUID

from sqlalchemy import Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.types.enum_types import PRINCIPAL_KIND_TYPE


class ApplicationAccountRow(AccessPersistenceBase):
    """Map a project-bound application principal."""

    __tablename__ = "application_accounts"

    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_kind: Mapped[PrincipalKind] = mapped_column(PRINCIPAL_KIND_TYPE, nullable=False)
