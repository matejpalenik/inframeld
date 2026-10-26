from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Float, Integer, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.application.enums.identity_recovery_cleanup_step import (
    IdentityRecoveryCleanupStep,
)
from inframeld_backend.access.application.enums.oauth_cleanup_category import OAuthCleanupCategory
from inframeld_backend.access.application.enums.oauth_cleanup_disposition import (
    OAuthCleanupDisposition,
)
from inframeld_backend.access.domain.enums.identity_recovery_cleanup_state import (
    IdentityRecoveryCleanupState,
)
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.types.enum_types import (
    IDENTITY_RECOVERY_CLEANUP_STATE_TYPE,
    IDENTITY_RECOVERY_CLEANUP_STEP_TYPE,
    OAUTH_CLEANUP_CATEGORY_TYPE,
    OAUTH_CLEANUP_DISPOSITION_TYPE,
)


class IdentityRecoveryCleanupStepRow(AccessPersistenceBase):
    """Retain only allowlisted observations for the two fixed Hydra operations."""

    __tablename__ = "identity_recovery_cleanup_steps"

    attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    step: Mapped[IdentityRecoveryCleanupStep] = mapped_column(
        IDENTITY_RECOVERY_CLEANUP_STEP_TYPE, primary_key=True
    )
    operation_id: Mapped[str] = mapped_column(Text, nullable=False)
    dispatched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    checkpointed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    state: Mapped[IdentityRecoveryCleanupState | None] = mapped_column(
        IDENTITY_RECOVERY_CLEANUP_STATE_TYPE, default=None
    )
    disposition: Mapped[OAuthCleanupDisposition | None] = mapped_column(
        OAUTH_CLEANUP_DISPOSITION_TYPE, default=None
    )
    category: Mapped[OAuthCleanupCategory | None] = mapped_column(
        OAUTH_CLEANUP_CATEGORY_TYPE, default=None
    )
    http_status: Mapped[int | None] = mapped_column(Integer, default=None)
    retry_after_seconds: Mapped[float | None] = mapped_column(Float, default=None)
