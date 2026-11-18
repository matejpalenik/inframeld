from uuid import UUID

from sqlalchemy import Integer, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from inframeld_backend.shared.infrastructure.rows.shared_persistence_base import (
    SharedPersistenceBase,
)


class ParsedPdfChunkRow(SharedPersistenceBase):
    """Keep an ordered, half-open code-point range in the generation's canonical text."""

    __tablename__ = "parsed_pdf_chunks"

    generation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_codepoint: Mapped[int] = mapped_column(Integer)
    end_codepoint: Mapped[int] = mapped_column(Integer)
