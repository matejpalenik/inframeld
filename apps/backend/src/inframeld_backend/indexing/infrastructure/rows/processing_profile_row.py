from uuid import UUID

from sqlalchemy import Boolean, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ProcessingProfileRow(SharedPersistenceBase):
    """Bind a fixed definition and Name to one Project and profile ID."""

    __tablename__ = "processing_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    docling_slim_version: Mapped[str] = mapped_column(String(32))
    docling_core_version: Mapped[str] = mapped_column(String(32))
    asset_manifest_sha256: Mapped[str] = mapped_column(String(64))
    max_content_tokens: Mapped[int] = mapped_column(Integer)
    merge_peers: Mapped[bool] = mapped_column(Boolean)
    repeat_table_header: Mapped[bool] = mapped_column(Boolean)
    ocr_enabled: Mapped[bool] = mapped_column(Boolean)
