from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, LargeBinary, String, Text, Uuid
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


def _enum_values(members: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in members]


_CLEANUP_STATE = SqlEnum(
    IdentityRecoveryCleanupState,
    native_enum=False,
    values_callable=_enum_values,
    length=16,
    validate_strings=True,
)


class HumanSuspensionObligationRow(SharedPersistenceBase):
    """Retain the original scope independently of child, native-request and live-link lifetimes."""

    __tablename__ = "human_suspension_obligations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), unique=True)
    operation_id: Mapped[str] = mapped_column(Text, unique=True)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    initiator_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    authority: Mapped[str] = mapped_column(Text)
    subject: Mapped[str] = mapped_column(Text)
    request_key: Mapped[str] = mapped_column(String(128))
    request_fingerprint: Mapped[bytes] = mapped_column(LargeBinary)
    before_access_revision: Mapped[int] = mapped_column(BigInteger)
    access_revision: Mapped[int] = mapped_column(BigInteger)
    admitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    queued_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_revision: Mapped[int] = mapped_column(BigInteger, default=1)
    kratos_sessions: Mapped[IdentityRecoveryCleanupState] = mapped_column(
        _CLEANUP_STATE, default=IdentityRecoveryCleanupState.PENDING
    )
    hydra_cli_grants: Mapped[IdentityRecoveryCleanupState] = mapped_column(
        _CLEANUP_STATE, default=IdentityRecoveryCleanupState.PENDING
    )
    hydra_remembered_logins: Mapped[IdentityRecoveryCleanupState] = mapped_column(
        _CLEANUP_STATE, default=IdentityRecoveryCleanupState.PENDING
    )
    queue_exhausted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
