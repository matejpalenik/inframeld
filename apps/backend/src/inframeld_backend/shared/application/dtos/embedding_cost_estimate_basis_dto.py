from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.embedding_estimate_connection_dto import (
    EmbeddingEstimateConnectionDTO,
)
from inframeld_backend.shared.application.dtos.model_metadata_source_dto import (
    ModelMetadataSourceDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO


@dataclass(frozen=True, slots=True)
class EmbeddingCostEstimateBasisDTO:
    """Freeze the advisory rate and its attribution before later quantity observations.

    A rate without a catalogue source is a reviewed override attributed to the
    captured settings fingerprint and capture time.
    """

    connection: EmbeddingEstimateConnectionDTO
    input_reference: str
    captured_at: datetime
    rate: SpendingRateDTO
    catalogue_source: ModelMetadataSourceDTO | None

    def __post_init__(self) -> None:
        if not self.input_reference.strip() or self.captured_at.utcoffset() is None:
            raise ValueError("An estimate basis requires its exact input and aware capture time.")
        if (self.rate.category, self.rate.unit) != ("input", "token"):
            raise ValueError("An embedding estimate basis requires a rate for input tokens.")
