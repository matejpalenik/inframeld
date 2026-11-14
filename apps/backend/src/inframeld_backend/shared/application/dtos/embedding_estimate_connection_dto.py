from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.model_selection_dto import ModelSelectionDTO
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


@dataclass(frozen=True, slots=True)
class EmbeddingEstimateConnectionDTO:
    """Carry exact connection facts from the trusted destination and adapter owner."""

    selection: ModelSelectionDTO
    settings_fingerprint: str
    access_revision: int
    official_openai_destination: bool
    official_openai_adapter: bool

    def __post_init__(self) -> None:
        RevisionValidation.require(self.access_revision)
        if not self.settings_fingerprint.strip():
            raise ValueError("An estimate connection requires reviewed settings.")
