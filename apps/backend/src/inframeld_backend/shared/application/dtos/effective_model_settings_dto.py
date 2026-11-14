from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.embedding_model_settings_dto import (
    EmbeddingModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.generation_model_settings_dto import (
    GenerationModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_token_bound_dto import ModelTokenBoundDTO
from inframeld_backend.shared.application.dtos.reranking_model_settings_dto import (
    RerankingModelSettingsDTO,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class EffectiveModelSettingsDTO:
    """Keep complete reviewed dispatch settings together, independently of suggested values."""

    context_tokens: int
    token_bound: ModelTokenBoundDTO
    settings: GenerationModelSettingsDTO | EmbeddingModelSettingsDTO | RerankingModelSettingsDTO

    def __post_init__(self) -> None:
        RevisionValidation.require(self.context_tokens)
        if self.context_tokens == 0:
            raise ValueError("A model context limit must be positive.")
        if (
            isinstance(self.settings, GenerationModelSettingsDTO)
            and self.settings.output_tokens > self.context_tokens
        ):
            raise ValueError("A generation output limit cannot exceed the model context limit.")
