"""Keep accounting quantities exact and make conservative rounding explicit."""

from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


@pytest.mark.parametrize("value", ["0", "1.230000000000", "-0.000000000001"])
def test_preserves_exact_signed_accounting_values(value: str) -> None:
    amount = Decimal(value)

    assert UsdAmount(amount).value == amount


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "0.000000000000"),
        ("0.7", "0.700000000000"),
        ("0.0000000000001", "0.000000000001"),
        ("1.000000000001", "1.000000000001"),
        ("1.0000000000011", "1.000000000002"),
    ],
)
def test_rounds_conservative_amounts_up_at_accounting_quantum(value: str, expected: str) -> None:
    rounded = UsdAmount.round_up(Decimal(value))

    assert rounded.value == Decimal(expected)


def test_rounding_does_not_inherit_lossy_decimal_context() -> None:
    value = Decimal("12345678901234567890.1234567890121")

    with localcontext() as context:
        context.prec = 8
        context.rounding = ROUND_DOWN
        rounded = UsdAmount.round_up(value)

    assert rounded.value == Decimal("12345678901234567890.123456789013")


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_rejects_nonfinite_stored_amounts(value: str) -> None:
    with pytest.raises(ValueError):
        UsdAmount(Decimal(value))


@pytest.mark.parametrize("value", ["NaN", "sNaN", "Infinity", "-Infinity"])
def test_rejects_nonfinite_rounding_inputs(value: str) -> None:
    with pytest.raises(ValueError):
        UsdAmount.round_up(Decimal(value))


@pytest.mark.parametrize("value", ["0.0000000000001", "-1.0000000000001"])
def test_construction_does_not_silently_round_extra_precision(value: str) -> None:
    with pytest.raises(ValueError):
        UsdAmount(Decimal(value))


def test_rejects_binary_floating_point_as_an_accounting_value() -> None:
    with pytest.raises(TypeError):
        UsdAmount(0.25)  # pyright: ignore[reportArgumentType]
