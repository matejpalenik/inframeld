from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)


class IdentityRecoveryProofLinkRow(AccessPersistenceBase):
    __tablename__ = "identity_recovery_proof_links"

    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authority: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    covering_operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    covered_operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
