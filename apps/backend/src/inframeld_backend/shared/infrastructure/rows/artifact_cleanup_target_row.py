from uuid import UUID

from sqlalchemy import Boolean, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ArtifactCleanupTargetRow(SharedPersistenceBase):
    __tablename__ = "artifact_cleanup_targets"

    obligation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    staging_confirmed_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    remote_confirmed_removed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
