from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)
from inframeld_backend.shared.application.dtos.spending_totals_dto import SpendingTotalsDTO
from inframeld_backend.shared.application.value_objects.spending_period import SpendingPeriod
from inframeld_backend.shared.domain.value_objects.usd_amount import UsdAmount


@dataclass(frozen=True, slots=True)
class SpendingProjectionDTO:
    """Return one coherent policy and captured-month accounting snapshot."""

    policy: ProjectSpendingPolicyDTO
    period: SpendingPeriod
    totals: SpendingTotalsDTO
    remaining: UsdAmount | None
