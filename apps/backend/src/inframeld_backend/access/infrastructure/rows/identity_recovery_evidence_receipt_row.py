from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.application.enums.identity_recovery_evidence_type import (
    IdentityRecoveryEvidenceType,
)
from inframeld_backend.access.infrastructure.rows.access_persistence_base import (
    AccessPersistenceBase,
)
from inframeld_backend.access.infrastructure.types.enum_types import (
    IDENTITY_RECOVERY_EVENT_KIND_TYPE,
    IDENTITY_RECOVERY_EVIDENCE_TYPE,
)


class IdentityRecoveryEvidenceReceiptRow(AccessPersistenceBase):
    __tablename__ = "identity_recovery_evidence_receipts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    authority: Mapped[str] = mapped_column(Text, nullable=False)
    subject: Mapped[str] = mapped_column(Text, nullable=False)
    operation_id: Mapped[str] = mapped_column(Text, nullable=False)
    event_type: Mapped[IdentityRecoveryEvidenceType] = mapped_column(
        IDENTITY_RECOVERY_EVIDENCE_TYPE, nullable=False
    )
    native_flow_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    session_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    source_recovery_flow_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    event_kind: Mapped[IdentityRecoveryEventKind | None] = mapped_column(
        IDENTITY_RECOVERY_EVENT_KIND_TYPE, nullable=True
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
