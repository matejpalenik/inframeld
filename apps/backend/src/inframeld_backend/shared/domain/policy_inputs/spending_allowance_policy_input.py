from dataclasses import dataclass

from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


@dataclass(frozen=True, slots=True)
class SpendingAllowancePolicyInput:
    """Supply accounting observations without establishing authority or a price bound.

    The accounting caller must establish complete conservatively bounded totals
    for every applicable cap before using this arithmetic input. Numeric holds
    cannot represent an unquantified earlier obligation. Project totals concern
    the captured UTC month. Operation totals remain cumulative across months.

    An absent limit is uncapped. An absent reservation amount describes only the
    new call's missing conservative bound and never means zero cost.
    """

    project_limit: UsdAmount | None
    project_settled: UsdAmount
    project_held: UsdAmount
    operation_limit: UsdAmount | None
    operation_settled: UsdAmount
    operation_held: UsdAmount
    reservation_amount: UsdAmount | None

    def __post_init__(self) -> None:
        amounts = (
            self.project_limit,
            self.project_settled,
            self.project_held,
            self.operation_limit,
            self.operation_settled,
            self.operation_held,
            self.reservation_amount,
        )
        if any(amount is not None and amount.value < 0 for amount in amounts):
            raise ValueError("Accounting costs, holds and limits cannot be negative.")
