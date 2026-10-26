from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.types.enum_types import (
    IDENTITY_RECOVERY_CLEANUP_STATE_TYPE,
)


class IdentityRecoveryCleanupJobRow(AccessPersistenceBase):
    __tablename__ = "identity_recovery_cleanup_jobs"

    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authority: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    evidence_receipt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    eligible_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    cli_grants_state: Mapped[IdentityRecoveryCleanupState] = mapped_column(
        IDENTITY_RECOVERY_CLEANUP_STATE_TYPE, init=False, server_default="pending"
    )
    remembered_logins_state: Mapped[IdentityRecoveryCleanupState] = mapped_column(
        IDENTITY_RECOVERY_CLEANUP_STATE_TYPE, init=False, server_default="pending"
    )
