from dataclasses import dataclass
from decimal import Decimal

from inframeld_backend.shared.application.dtos.embedding_cost_estimate_basis_dto import (
    EmbeddingCostEstimateBasisDTO,
)
from inframeld_backend.shared.application.dtos.embedding_input_quantity_dto import (
    EmbeddingInputQuantityDTO,
)
from inframeld_backend.shared.application.enums.embedding_cost_estimate_reason import (
    EmbeddingCostEstimateReason,
)


@dataclass(frozen=True, slots=True)
class EmbeddingCostEstimateDTO:
    """Report an advisory amount or the missing prerequisite with captured evidence."""

    amount_usd: Decimal | None
    reason: EmbeddingCostEstimateReason | None
    basis: EmbeddingCostEstimateBasisDTO | None = None
    quantity: EmbeddingInputQuantityDTO | None = None

    def __post_init__(self) -> None:
        if (self.amount_usd is None) == (self.reason is None):
            raise ValueError("An estimate requires an amount or an explicit unknown reason.")
        if self.amount_usd is not None and (self.basis is None or self.quantity is None):
            raise ValueError("An estimated amount requires its price and quantity evidence.")
