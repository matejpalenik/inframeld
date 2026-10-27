from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.application.enums.identity_recovery_run_source import (
    IdentityRecoveryRunSource,
)
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.types.enum_types import (
    IDENTITY_RECOVERY_RUN_SOURCE_TYPE,
)


class IdentityRecoveryCleanupRunRow(AccessPersistenceBase):
    __tablename__ = "identity_recovery_cleanup_runs"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    operation_id: Mapped[str] = mapped_column(Text, nullable=False)
    authorization_source: Mapped[IdentityRecoveryRunSource] = mapped_column(
        IDENTITY_RECOVERY_RUN_SOURCE_TYPE, nullable=False
    )
    authorized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_attempts: Mapped[int] = mapped_column(Integer, init=False, server_default="12")
    consumed_attempts: Mapped[int] = mapped_column(Integer, init=False, server_default="0")
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    terminal_reason: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
