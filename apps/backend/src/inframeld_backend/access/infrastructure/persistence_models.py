"""ORM mappings used by Access persistence adapters.

Alembic migrations remain responsible for creating and constraining the database schema.
"""

from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID

from sqlalchemy import Boolean, DateTime, Enum, Integer, String, Text, Uuid, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from inframeld_backend.access.domain.values import PrincipalKind, PrincipalStatus, ProjectStatus


def _enum_values(members: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in members]


_PRINCIPAL_KIND_TYPE = Enum(
    PrincipalKind,
    native_enum=False,
    values_callable=_enum_values,
    length=20,
    validate_strings=True,
)
_PRINCIPAL_STATUS_TYPE = Enum(
    PrincipalStatus,
    native_enum=False,
    values_callable=_enum_values,
    length=20,
    validate_strings=True,
)
_PROJECT_STATUS_TYPE = Enum(
    ProjectStatus,
    native_enum=False,
    values_callable=_enum_values,
    length=20,
    validate_strings=True,
)


class AccessPersistenceBase(DeclarativeBase):
    """Base for Access database row mappings."""


class OrganizationRow(AccessPersistenceBase):
    """Map an installation organization used by Access records."""

    __tablename__ = "organizations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    access_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class PrincipalRow(AccessPersistenceBase):
    """Map a human or application principal stored in PostgreSQL."""

    __tablename__ = "principals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    kind: Mapped[PrincipalKind] = mapped_column(_PRINCIPAL_KIND_TYPE, nullable=False)
    status: Mapped[PrincipalStatus] = mapped_column(_PRINCIPAL_STATUS_TYPE, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ProjectRow(AccessPersistenceBase):
    """Map a project whose membership and permissions Access checks."""

    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ProjectStatus] = mapped_column(_PROJECT_STATUS_TYPE, nullable=False)
    access_revision: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="0",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class ApplicationAccountRow(AccessPersistenceBase):
    """Map a project-bound application principal."""

    __tablename__ = "application_accounts"

    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_kind: Mapped[PrincipalKind] = mapped_column(_PRINCIPAL_KIND_TYPE, nullable=False)


class ProjectMembershipRow(AccessPersistenceBase):
    """Map a principal's membership in a project."""

    __tablename__ = "project_memberships"

    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_kind: Mapped[PrincipalKind] = mapped_column(_PRINCIPAL_KIND_TYPE, nullable=False)
    application_principal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    assigned_by_principal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )


class ProjectActionGrantRow(AccessPersistenceBase):
    """Map one action granted to a principal on a project."""

    __tablename__ = "project_action_grants"

    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    recipient_principal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )
    recipient_kind: Mapped[PrincipalKind] = mapped_column(_PRINCIPAL_KIND_TYPE, nullable=False)
    action: Mapped[str] = mapped_column(String(100), primary_key=True)
    can_grant: Mapped[bool] = mapped_column(Boolean, nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    assigned_by_principal_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        nullable=True,
    )


class HumanIdentityLinkRow(AccessPersistenceBase):
    """Map a verified identity to its local human principal."""

    __tablename__ = "human_identity_links"

    authority: Mapped[str] = mapped_column(Text, primary_key=True)
    subject: Mapped[str] = mapped_column(Text, primary_key=True)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    principal_kind: Mapped[PrincipalKind] = mapped_column(_PRINCIPAL_KIND_TYPE, nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
