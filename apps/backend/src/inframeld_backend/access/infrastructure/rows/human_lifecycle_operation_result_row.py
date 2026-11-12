from enum import Enum as PythonEnum
from uuid import UUID

from sqlalchemy import BigInteger, Boolean, Text, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


def _enum_values(members: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in members]


_ACTION_TYPE = SqlEnum(
    OrganizationAction,
    native_enum=False,
    values_callable=_enum_values,
    length=32,
    validate_strings=True,
)


class HumanLifecycleOperationResultRow(AccessPersistenceBase):
    """Store safe original outcome fields without retaining credentials or review text."""

    __tablename__ = "human_lifecycle_operation_results"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    action_id: Mapped[OrganizationAction] = mapped_column(_ACTION_TYPE)
    before_revision: Mapped[int] = mapped_column(BigInteger)
    access_revision: Mapped[int] = mapped_column(BigInteger)
    changed: Mapped[bool] = mapped_column(Boolean)
    cleanup_operation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), default=None)
    before_credential_version: Mapped[int | None] = mapped_column(BigInteger, default=None)
    credential_version: Mapped[int | None] = mapped_column(BigInteger, default=None)
