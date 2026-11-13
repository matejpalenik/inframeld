from dataclasses import dataclass, field
from typing import Literal

from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class RerankingModelSettingsDTO:
    """Bound the number of candidates a hosted reranking request may submit."""

    maximum_candidates: int
    role: Literal[ModelRole.RERANKING] = field(kw_only=True)

    def __post_init__(self) -> None:
        RevisionValidation.require(self.maximum_candidates)
        if self.maximum_candidates == 0:
            raise ValueError("A reranking candidate limit must be positive.")
