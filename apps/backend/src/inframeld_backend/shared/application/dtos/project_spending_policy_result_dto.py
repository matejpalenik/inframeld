from dataclasses import dataclass

from inframeld_backend.shared.application.dtos.completed_synchronous_operation_dto import (
    CompletedSynchronousOperationDTO,
)
from inframeld_backend.shared.application.dtos.project_spending_policy_dto import (
    ProjectSpendingPolicyDTO,
)


@dataclass(frozen=True, slots=True)
class ProjectSpendingPolicyResultDTO:
    """Keep the original policy result separate from current accounting observations."""

    policy: ProjectSpendingPolicyDTO
    completion: CompletedSynchronousOperationDTO
    changed: bool
