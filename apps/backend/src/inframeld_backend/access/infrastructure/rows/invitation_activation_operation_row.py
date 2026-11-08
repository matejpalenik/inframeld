from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, LargeBinary, String, Text, Uuid, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.shared.application.enums.operation_reservation_state import (
    OperationReservationState,
)


def _enum_values(members: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in members]


class InvitationActivationOperationRow(AccessPersistenceBase):
    """Retain identity-bound activation independently of issuance and invitation expiry.

    A pending recipient may be absent. Completion requires the resulting stable
    principal and original revisions, with one nonrenewed database completion expiry.
    """

    __tablename__ = "invitation_activation_operations"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    authority: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    invitation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    issuer_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    method: Mapped[str] = mapped_column(String(16))
    requested_route: Mapped[str] = mapped_column(Text)
    request_key: Mapped[str] = mapped_column(String(128))
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary, repr=False)
    principal_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    state: Mapped[OperationReservationState] = mapped_column(
        SqlEnum(
            OperationReservationState,
            native_enum=False,
            values_callable=_enum_values,
        ),
        init=False,
        server_default=OperationReservationState.IN_PROGRESS.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.clock_timestamp()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    organization_access_revision: Mapped[int | None] = mapped_column(BigInteger, default=None)
    project_access_revisions: Mapped[list[dict[str, object]] | None] = mapped_column(
        JSONB(none_as_null=True), default=None
    )
