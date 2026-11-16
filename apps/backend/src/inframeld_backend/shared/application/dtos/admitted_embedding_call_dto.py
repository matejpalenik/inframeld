from dataclasses import dataclass, field

from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.reviewed_model_settings_dto import (
    ReviewedModelSettingsDTO,
)
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


@dataclass(frozen=True, slots=True)
class AdmittedEmbeddingCallDTO:
    """Carry the original reviewed selection, qualified tokens and captured pricing."""

    reviewed: ReviewedModelSettingsDTO
    access_revision: int
    tokens: tuple[int, ...] = field(repr=False)
    basis: CapturedSpendingBasisDTO
    operation_limit: UsdAmount | None
