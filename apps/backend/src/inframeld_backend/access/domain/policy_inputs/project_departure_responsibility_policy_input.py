from dataclasses import dataclass
from typing import Literal

from inframeld_backend.access.domain.policy_inputs.project_departure_candidate_policy_input import (
    ProjectDepartureCandidatePolicyInput,
)
from inframeld_backend.access.domain.value_objects.action_id import ActionId


@dataclass(frozen=True, slots=True)
class ProjectDepartureResponsibilityPolicyInput:
    """Keep management and exact-action delegation alternatives explicit."""

    target_kind: Literal["project", "access_group", "application_account"]
    action_id: ActionId | None
    candidates: tuple[ProjectDepartureCandidatePolicyInput, ...]
