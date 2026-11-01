from inframeld_backend.access.domain.enums.project_status import ProjectStatus
from inframeld_backend.access.domain.policies.human_authentication_policy import (
    HumanAuthenticationPolicy,
)
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class ProjectMetadataRepairPolicy:
    @staticmethod
    def may_assign(
        *,
        recipient_access: PrincipalAccessPolicyInput,
        is_project_member: bool,
        project_status: ProjectStatus,
        eligible_grantor_exists: bool | None,
    ) -> bool:
        return (
            HumanAuthenticationPolicy.may_authenticate(recipient_access)
            and is_project_member
            and project_status is ProjectStatus.ACTIVE
            and eligible_grantor_exists is False
        )
