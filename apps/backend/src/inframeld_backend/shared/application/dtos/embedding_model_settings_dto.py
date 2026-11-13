from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.shared.application.enums.embedding_distance import EmbeddingDistance
from inframeld_backend.shared.application.enums.embedding_normalization import (
    EmbeddingNormalization,
)
from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class EmbeddingModelSettingsDTO:
    """Freeze expected vector shape, distance and exact document and query input prefixes."""

    dimensions: int
    normalization: EmbeddingNormalization
    distance: EmbeddingDistance
    document_prefix: str
    query_prefix: str
    expected_provider: str
    expected_model_revision: str | None = None
    role: Literal[ModelRole.EMBEDDING] = field(kw_only=True)

    def __post_init__(self) -> None:
        if not self.expected_provider.strip():
            raise ValueError("Embedding settings require an expected provider identity.")
        if self.expected_model_revision is not None and not self.expected_model_revision.strip():
            raise ValueError("An expected embedding model revision cannot be blank.")
        RevisionValidation.require(self.dimensions)
        if self.dimensions == 0:
            raise ValueError("Expected embedding dimensions must be positive.")
