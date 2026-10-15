from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.types.enum_types import (
    IDENTITY_RECOVERY_CLEANUP_STATE_TYPE,
    IDENTITY_RECOVERY_EVENT_KIND_TYPE,
)


class IdentityRecoveryAdmissionRow(AccessPersistenceBase):
    """Keep the original operation and its block until this row is explicitly released."""

    __tablename__ = "identity_recovery_admissions"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authority: Mapped[str] = mapped_column(Text, nullable=False)
    flow_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    event_kind: Mapped[IdentityRecoveryEventKind] = mapped_column(
        IDENTITY_RECOVERY_EVENT_KIND_TYPE, nullable=False
    )
    kratos_cleanup_state: Mapped[IdentityRecoveryCleanupState] = mapped_column(
        IDENTITY_RECOVERY_CLEANUP_STATE_TYPE,
        nullable=False,
        init=False,
        server_default="pending",
    )
    hydra_cleanup_state: Mapped[IdentityRecoveryCleanupState] = mapped_column(
        IDENTITY_RECOVERY_CLEANUP_STATE_TYPE,
        nullable=False,
        init=False,
        server_default="pending",
    )
    admitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, init=False, server_default=func.now()
    )
    released_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, init=False, default=None
    )
