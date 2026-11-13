from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO


@dataclass(frozen=True, slots=True)
class ModelPricingDTO:
    """Describe available exact rates by billable category and unit.

    Only a qualified local observation can establish no external API charge.
    Category completeness and suitability for spending admission remain caller checks.
    """

    rates: tuple[SpendingRateDTO, ...]
    qualified_local_no_external_charge: bool = False

    def __post_init__(self) -> None:
        keys = {(rate.category, rate.unit) for rate in self.rates}
        if self.qualified_local_no_external_charge and any(
            rate.usd_per_unit != 0 for rate in self.rates
        ):
            raise ValueError("A qualified local observation cannot contain a nonzero charge.")
        if len(keys) != len(self.rates) or (
            not keys and not self.qualified_local_no_external_charge
        ):
            raise ValueError("Model rates require one or more unique category and unit pairs.")
