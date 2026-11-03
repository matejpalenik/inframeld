from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_ACCOUNTING_SCALE = 10**12


@dataclass(frozen=True, slots=True)
class UsdAmount:
    """Represent exact USD accounting values independently of display rounding."""

    value: Decimal

    def __post_init__(self) -> None:
        value = UsdAmount._require_finite_decimal(self.value)
        numerator, denominator = value.as_integer_ratio()
        if numerator * _ACCOUNTING_SCALE % denominator:
            raise ValueError("An accounting amount must be exact at the USD quantum.")

    @staticmethod
    def round_up(value: Decimal) -> UsdAmount:
        """Convert a finite amount upward at the twelve-decimal accounting quantum."""
        value = UsdAmount._require_finite_decimal(value)
        numerator, denominator = value.as_integer_ratio()
        units = -(-(numerator * _ACCOUNTING_SCALE) // denominator)
        representation = Decimal(units).as_tuple()
        rounded = Decimal((representation.sign, representation.digits, -12))

        return UsdAmount(rounded)

    @staticmethod
    def _require_finite_decimal(value: object) -> Decimal:
        if not isinstance(value, Decimal):
            raise TypeError("An accounting amount must be a Decimal.")
        if not value.is_finite():
            raise ValueError("An accounting amount must be finite.")

        return value
