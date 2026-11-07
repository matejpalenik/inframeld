from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class ApplicationAuthenticationPolicy:
    """Admit only an active application coherently bound to its active Project."""

    @staticmethod
    def may_authenticate(
        *,
        principal_access: PrincipalAccessPolicyInput,
        project_status: ProjectStatus,
        is_project_member: bool,
        has_coherent_binding: bool,
    ) -> bool:
        return (
            principal_access.principal.kind is PrincipalKind.APPLICATION
            and PrincipalAccessPolicy.may_use_product(principal_access)
            and project_status is ProjectStatus.ACTIVE
            and is_project_member
            and has_coherent_binding
        )
