from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, LargeBinary, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ParsedPdfGenerationRow(SharedPersistenceBase):
    """Bind one original preparation to exact source, profile and canonical bytes."""

    __tablename__ = "parsed_pdf_generations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    document_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    document_version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    processing_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    canonical_artifact_attempt_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    canonical_identity: Mapped[bytes] = mapped_column(LargeBinary, repr=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
