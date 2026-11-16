from uuid import UUID

from sqlalchemy import BigInteger, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class EmbeddingProfileRow(SharedPersistenceBase):
    __tablename__ = "embedding_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    project_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    organization_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    name: Mapped[str] = mapped_column(Text)
    display_name: Mapped[str] = mapped_column(Text)
    model_connection_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    model_alias: Mapped[str] = mapped_column(Text)
    expected_provider: Mapped[str] = mapped_column(Text)
    expected_model_revision: Mapped[str | None] = mapped_column(Text)
    dimensions: Mapped[int] = mapped_column(Integer)
    normalization: Mapped[str] = mapped_column(String(32))
    distance: Mapped[str] = mapped_column(String(32))
    document_prefix: Mapped[str] = mapped_column(Text)
    query_prefix: Mapped[str] = mapped_column(Text)
    context_tokens: Mapped[int] = mapped_column(BigInteger)
    token_bound_kind: Mapped[str] = mapped_column(String(32))
    token_bound_implementation: Mapped[str] = mapped_column(Text)
    token_bound_revision: Mapped[str] = mapped_column(Text)
    settings_fingerprint: Mapped[str] = mapped_column(String(64))
    vector_index_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    vector_layout_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True))
    placement_version: Mapped[int] = mapped_column(Integer)
    shard_count: Mapped[int] = mapped_column(Integer)
    shard_zero_name: Mapped[str] = mapped_column(String(63))
    shard_one_name: Mapped[str] = mapped_column(String(63))
