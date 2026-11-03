from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class SpendingUsageDTO:
    """Carry a canonical quantity without normalizing a provider response."""

    category: str
    unit: str
    quantity: Decimal

    def __post_init__(self) -> None:
        if not self.category.strip() or not self.unit.strip():
            raise ValueError("Spending usage requires a category and unit.")
        self._require_quantity(self.quantity)

    @staticmethod
    def _require_quantity(value: object) -> None:
        if not isinstance(value, Decimal):
            raise TypeError("Spending usage requires an exact decimal.")
        if not value.is_finite() or value < 0:
            raise ValueError("Spending usage must be finite and nonnegative.")
