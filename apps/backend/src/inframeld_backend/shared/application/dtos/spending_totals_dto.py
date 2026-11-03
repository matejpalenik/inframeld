from dataclasses import dataclass

from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


@dataclass(frozen=True, slots=True)
class SpendingTotalsDTO:
    """Separate known amounts from obligations that cannot yet be quantified."""

    settled: UsdAmount
    held: UsdAmount
    unquantified_holds: int

    def __post_init__(self) -> None:
        if self.settled.value < 0 or self.held.value < 0:
            raise ValueError("Settled spending and held amounts cannot be negative.")
        if type(self.unquantified_holds) is not int or self.unquantified_holds < 0:
            raise ValueError("Unquantified holds require a nonnegative count.")
