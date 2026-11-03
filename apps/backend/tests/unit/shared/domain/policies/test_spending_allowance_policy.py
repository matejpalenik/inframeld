"""Count settled amounts and unresolved holds against both supplied limits.

These pure decisions assume complete conservatively bounded applicable totals.
They do not establish provider bounds, the absence of unquantified obligations
or concurrent PostgreSQL admission. An absent new-call amount is not a prior
unknown hold. Project and cumulative operation scopes remain caller obligations.
"""

from dataclasses import replace
from decimal import ROUND_DOWN, Decimal, localcontext

import pytest

from inframeld_backend.shared.domain.policies.spending_allowance_policy import (
    SpendingAllowancePolicy,
)
from inframeld_backend.shared.domain.policy_inputs.spending_allowance_policy_input import (
    SpendingAllowancePolicyInput,
)
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


def _amount(value: str | None) -> UsdAmount | None:
    return UsdAmount(Decimal(value)) if value is not None else None


def _input(
    *,
    project_limit: str | None = "1",
    project_settled: str = "0",
    project_held: str = "0",
    operation_limit: str | None = "1",
    operation_settled: str = "0",
    operation_held: str = "0",
    reservation_amount: str | None = "0.1",
) -> SpendingAllowancePolicyInput:
    return SpendingAllowancePolicyInput(
        project_limit=_amount(project_limit),
        project_settled=UsdAmount(Decimal(project_settled)),
        project_held=UsdAmount(Decimal(project_held)),
        operation_limit=_amount(operation_limit),
        operation_settled=UsdAmount(Decimal(operation_settled)),
        operation_held=UsdAmount(Decimal(operation_held)),
        reservation_amount=_amount(reservation_amount),
    )


def test_settled_amounts_and_holds_can_leave_exactly_the_requested_allowance() -> None:
    state = _input(
        project_settled="0.6",
        project_held="0.3",
        operation_settled="0.7",
        operation_held="0.2",
    )

    assert SpendingAllowancePolicy.can_reserve(state)


@pytest.mark.parametrize("limited_scope", ["project", "operation"])
def test_one_additional_quantum_cannot_spend_already_held_allowance(limited_scope: str) -> None:
    state = (
        _input(project_settled="0.6", project_held="0.3")
        if limited_scope == "project"
        else _input(operation_settled="0.6", operation_held="0.3")
    )
    state = replace(state, reservation_amount=UsdAmount(Decimal("0.100000000001")))

    assert not SpendingAllowancePolicy.can_reserve(state)


def test_operation_allowance_remains_independent_of_available_project_allowance() -> None:
    state = _input(
        project_limit="100",
        operation_settled="0.8",
        operation_held="0.2",
    )

    assert not SpendingAllowancePolicy.can_reserve(state)


def test_a_lower_project_limit_keeps_existing_costs_and_holds_effective() -> None:
    state = _input(project_limit="0.5", project_settled="0.6", reservation_amount="0")

    assert not SpendingAllowancePolicy.can_reserve(state)


@pytest.mark.parametrize("reservation_amount", ["0", "0.000000000001"])
def test_zero_allowance_is_distinct_from_an_absent_limit(reservation_amount: str) -> None:
    state = _input(project_limit="0", operation_limit=None, reservation_amount=reservation_amount)

    assert SpendingAllowancePolicy.can_reserve(state) is (reservation_amount == "0")


@pytest.mark.parametrize(
    ("project_limit", "operation_limit"), [("1", None), (None, "1"), ("1", "1")]
)
def test_either_cap_requires_a_supplied_conservative_amount(
    project_limit: str | None, operation_limit: str | None
) -> None:
    state = _input(
        project_limit=project_limit,
        operation_limit=operation_limit,
        reservation_amount=None,
    )

    assert not SpendingAllowancePolicy.can_reserve(state)


def test_uncapped_unknown_pricing_does_not_become_a_zero_cost_observation() -> None:
    state = _input(project_limit=None, operation_limit=None, reservation_amount=None)

    assert SpendingAllowancePolicy.can_reserve(state)
    assert state.reservation_amount is None


def test_allowance_comparison_preserves_one_quantum_under_a_lossy_decimal_context() -> None:
    state = _input(
        project_limit="12345678901234567890.000000000000",
        project_settled="12345678901234567889.999999999999",
        operation_limit=None,
        reservation_amount="0.000000000002",
    )

    with localcontext() as context:
        context.prec = 8
        context.rounding = ROUND_DOWN
        allowed = SpendingAllowancePolicy.can_reserve(state)

    assert not allowed


@pytest.mark.parametrize(
    "field_name",
    [
        "project_limit",
        "project_settled",
        "project_held",
        "operation_limit",
        "operation_settled",
        "operation_held",
        "reservation_amount",
    ],
)
def test_negative_costs_holds_or_limits_cannot_create_allowance(field_name: str) -> None:
    state = _input()

    with pytest.raises(ValueError):
        replace(state, **{field_name: UsdAmount(Decimal("-0.000000000001"))})
