from dataclasses import dataclass

from inframeld_backend.access.domain.entities.principal import Principal
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


@dataclass(frozen=True, slots=True)
class ProjectGrantChangeFactsDTO:
    """Current grant facts observed while the Access change locks are held."""

    actor_access: PrincipalAccessPolicyInput
    recipient: Principal | None
    project_status: ProjectStatus
    project_access_revision: int
    actor_is_project_member: bool
    recipient_is_project_member: bool
    actor_can_grant_action: bool
