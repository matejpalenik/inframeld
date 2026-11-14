from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO


@dataclass(frozen=True, slots=True)
class EmbeddingInputQuantityDTO:
    """Carry an already saved token observation for an exact assessed input and profile."""

    selection: ModelSelectionDTO
    input_reference: str
    settings_fingerprint: str
    source_reference: str
    source_revision: str
    observed_at: datetime
    usage: SpendingUsageDTO

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.input_reference,
                self.settings_fingerprint,
                self.source_reference,
                self.source_revision,
            )
        ):
            raise ValueError("Saved embedding input requires its exact input, settings and source.")
        if self.observed_at.utcoffset() is None:
            raise ValueError("Saved embedding input requires an aware observation time.")
        if (self.usage.category, self.usage.unit) != (
            "input",
            "token",
        ) or self.usage.quantity != self.usage.quantity.to_integral_value():
            raise ValueError("Saved embedding quantity requires whole input tokens.")
