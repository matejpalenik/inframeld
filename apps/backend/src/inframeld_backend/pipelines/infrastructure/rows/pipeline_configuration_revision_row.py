from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class PipelineConfigurationRevisionRow(SharedPersistenceBase):
    """Retain one immutable, scoped working configuration."""

    __tablename__ = "pipeline_configuration_revisions"

    pipeline_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    revision: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    installation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    collection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    processing_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    embedding_profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    model_connection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    model_alias: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text, repr=False)
    reranker: Mapped[str] = mapped_column(Text)
    top_k: Mapped[int] = mapped_column(BigInteger)
    max_passages: Mapped[int] = mapped_column(BigInteger)
    output_tokens: Mapped[int] = mapped_column(BigInteger)
    created_by_principal_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), init=False, server_default=func.now()
    )
