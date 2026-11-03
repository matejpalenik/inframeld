from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from inframeld_backend.shared.application.dtos.captured_spending_basis_dto import (
    CapturedSpendingBasisDTO,
)
from inframeld_backend.shared.application.dtos.spending_rate_dto import SpendingRateDTO
from inframeld_backend.shared.application.dtos.spending_usage_dto import SpendingUsageDTO

NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _basis() -> CapturedSpendingBasisDTO:
    return CapturedSpendingBasisDTO(
        "basis-1",
        "fixture-pricing",
        "revision-1",
        NOW,
        (SpendingRateDTO("input", "unit", Decimal("0.000000000000001")),),
        (SpendingUsageDTO("input", "unit", Decimal("1000.00000000000001")),),
    )


def test_preserves_below_quantum_rates_and_fractional_quantities() -> None:
    basis = _basis()

    assert basis.rates[0].usd_per_unit == Decimal("0.000000000000001")
    assert basis.maximum_usage is not None
    assert basis.maximum_usage[0].quantity == Decimal("1000.00000000000001")


@pytest.mark.parametrize("value", ["-1", "NaN", "sNaN", "Infinity"])
def test_rejects_unusable_rates_and_quantities(value: str) -> None:
    with pytest.raises(ValueError):
        SpendingRateDTO("input", "unit", Decimal(value))

    with pytest.raises(ValueError):
        SpendingUsageDTO("input", "unit", Decimal(value))


def test_unknown_bound_is_retained_without_fabricating_zero_usage() -> None:
    basis = replace(_basis(), maximum_usage=None)

    assert basis.maximum_usage is None


def test_rejects_duplicate_rate_meaning() -> None:
    basis = _basis()

    with pytest.raises(ValueError):
        replace(basis, rates=basis.rates + basis.rates)


def test_rejects_a_partial_or_wrong_unit_upper_bound() -> None:
    basis = _basis()

    with pytest.raises(ValueError):
        replace(basis, maximum_usage=())

    with pytest.raises(ValueError):
        replace(basis, maximum_usage=(SpendingUsageDTO("input", "different-unit", Decimal("1")),))


def test_rejects_unattributed_or_naive_basis() -> None:
    basis = _basis()

    with pytest.raises(ValueError):
        replace(basis, source_reference="")

    with pytest.raises(ValueError):
        replace(basis, captured_at=NOW.replace(tzinfo=None))
