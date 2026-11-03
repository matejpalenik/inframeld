from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SpendingRateDTO:
    """Capture a canonical rate at its original precision, not the money quantum."""

    category: str
    unit: str
    usd_per_unit: Decimal

    def __post_init__(self) -> None:
        if not self.category.strip() or not self.unit.strip():
            raise ValueError("A spending rate requires a category and unit.")
        self._require_rate(self.usd_per_unit)

    @staticmethod
    def _require_rate(value: object) -> None:
        if not isinstance(value, Decimal):
            raise TypeError("A spending rate requires an exact decimal.")
        if not value.is_finite() or value < 0:
            raise ValueError("A spending rate must be finite and nonnegative.")
