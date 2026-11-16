from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, String, Text, Uuid
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class DocumentUploadRow(SharedPersistenceBase):
    __tablename__ = "document_uploads"

    operation_id: Mapped[str] = mapped_column(Text, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    actor_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    request_key: Mapped[str] = mapped_column(String(128), repr=False)
    request_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    artifact_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    reservation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    obligation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    cleanup_job_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    filename: Mapped[str] = mapped_column(Text, repr=False)
    group_ids: Mapped[list[UUID]] = mapped_column(ARRAY(Uuid(as_uuid=True)))
    state: Mapped[str] = mapped_column(String(16))
    replay_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )
