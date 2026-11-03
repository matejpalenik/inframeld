from dataclasses import dataclass
from datetime import datetime

from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO


@dataclass(frozen=True, slots=True)
class CapturedSpendingBasisDTO:
    """Retain declared pricing and optional maximum quantities for one call.

    Qualified callers own category coverage, pricing currentness and provenance.
    Construction proves none of those external facts and triggers no model call.
    """

    basis_id: str
    source_reference: str
    source_revision: str
    captured_at: datetime
    rates: tuple[SpendingRateDTO, ...]
    maximum_usage: tuple[SpendingUsageDTO, ...] | None

    def __post_init__(self) -> None:
        if any(
            not value.strip()
            for value in (self.basis_id, self.source_reference, self.source_revision)
        ):
            raise ValueError("A captured spending basis requires source identity and revision.")
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("A captured spending basis requires an aware capture time.")
        keys = {(rate.category, rate.unit) for rate in self.rates}
        if not keys or len(keys) != len(self.rates):
            raise ValueError("A captured spending basis requires unique rate keys.")
        if self.maximum_usage is not None:
            usage_keys = {(usage.category, usage.unit) for usage in self.maximum_usage}
            if len(usage_keys) != len(self.maximum_usage) or usage_keys != keys:
                raise ValueError("Maximum usage must cover every captured rate exactly once.")
