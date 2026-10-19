from dataclasses import dataclass

from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


@dataclass(frozen=True, slots=True)
class ProjectActionFactsDTO:
    """Current caller and project facts for one authorization attempt.

    The reader establishes the organization match. The service decides
    visibility and permission from these facts.
    """

    principal_access: PrincipalAccessPolicyInput
    project_status: ProjectStatus
    is_project_member: bool
    has_exact_action_grant: bool
