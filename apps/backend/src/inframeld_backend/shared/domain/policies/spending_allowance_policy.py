from fractions import Fraction

from inframeld_backend.shared.domain.policy_inputs.spending_allowance_policy_input import (
    SpendingAllowancePolicyInput,
)
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


class SpendingAllowancePolicy:
    """Compare complete conservatively bounded totals with applicable allowances.

    The accounting caller must first reject incomplete facts for an applicable
    cap, including unquantified original obligations. This arithmetic decision
    alone cannot establish reservation or dispatch admission.
    """

    @staticmethod
    def can_reserve(policy_input: SpendingAllowancePolicyInput) -> bool:
        """Check settled amounts and holds without reserving money or authorizing dispatch."""
        amount = policy_input.reservation_amount
        if amount is None:
            return policy_input.project_limit is None and policy_input.operation_limit is None

        return SpendingAllowancePolicy._fits(
            policy_input.project_limit,
            policy_input.project_settled,
            policy_input.project_held,
            amount,
        ) and SpendingAllowancePolicy._fits(
            policy_input.operation_limit,
            policy_input.operation_settled,
            policy_input.operation_held,
            amount,
        )

    @staticmethod
    def _fits(
        limit: UsdAmount | None, settled: UsdAmount, held: UsdAmount, amount: UsdAmount
    ) -> bool:
        if limit is None:
            return True

        total = Fraction(settled.value) + Fraction(held.value) + Fraction(amount.value)
        return total <= Fraction(limit.value)
