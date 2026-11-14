from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.adopted_model_suggestion_dto import (
    AdoptedModelSuggestionDTO,
)
from inframeld_backend.shared.application.dtos.effective_model_settings_dto import (
    EffectiveModelSettingsDTO,
)
from inframeld_backend.shared.application.dtos.model_metadata_dto import ModelMetadataDTO
from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO


@dataclass(frozen=True, slots=True)
class ReviewedModelSettingsDTO:
    """Bind effective settings to their consumer's model choice and settings fingerprint."""

    selection: ModelSelectionDTO
    effective: EffectiveModelSettingsDTO
    fingerprint: str
    suggestions: ModelMetadataDTO | None = None
    adopted_suggestions: tuple[AdoptedModelSuggestionDTO, ...] = ()
    price_overrides: tuple[SpendingRateDTO, ...] = ()

    def __post_init__(self) -> None:
        if self.selection.role is not self.effective.settings.role or not self.fingerprint.strip():
            raise ValueError("Reviewed model settings require a matching role and fingerprint.")
        if self.suggestions is not None and self.suggestions.selection != self.selection:
            raise ValueError("Reviewed suggestions must describe the same model selection.")

        adopted_properties = {item.property for item in self.adopted_suggestions}
        if len(adopted_properties) != len(self.adopted_suggestions):
            raise ValueError("A reviewed property can have only one adopted source.")
        for item in self.adopted_suggestions:
            if self.suggestions is None or not self.suggestions.has_suggestion(
                self.effective, item.property, item.source
            ):
                raise ValueError("An adopted source must supply the exact reviewed property value.")

        price_keys = {(rate.category, rate.unit) for rate in self.price_overrides}
        if len(price_keys) != len(self.price_overrides):
            raise ValueError("Explicit price overrides require unique category and unit pairs.")
