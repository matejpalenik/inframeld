from dataclasses import dataclass

from inframeld_backend.indexing.application.dtos.embedding_profile_dto import EmbeddingProfileDTO


@dataclass(frozen=True, slots=True)
class EmbeddingProfilePageDTO:
    items: tuple[EmbeddingProfileDTO, ...]
    next_cursor: str | None
