from dataclasses import dataclass

from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)


@dataclass(frozen=True, slots=True)
class ProjectDepartureResponsibilityPolicyInput:
    """Keep management and exact-action delegation alternatives explicit."""

    requires_group_manager: bool
    allows_group_manager: bool
    candidates: tuple[ProjectDepartureCandidatePolicyInput, ...]
