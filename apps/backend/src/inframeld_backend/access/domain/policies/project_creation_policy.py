from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class ProjectCreationPolicy:
    INITIAL_ACTIONS = (
        "manage-project-members",
        "create-access-groups",
        "create-application-accounts",
        "create-pipelines",
        "create-deployments",
        "manage-upload-defaults",
        "delete-project",
        "inspect-budget",
        "manage-budget",
        "manage-trace-policy",
        "delete-trace-history",
        "inspect-feedback",
        "create-collections",
        "create-sources",
        "create-model-connections",
        "create-processing-profiles",
        "create-embedding-profiles",
        "edit-project-metadata",
    )

    @staticmethod
    def may_create(eligibility: PrincipalAccessPolicyInput, *, has_create_projects: bool) -> bool:
        return (
            eligibility.principal.kind is PrincipalKind.HUMAN
            and PrincipalAccessPolicy.may_use_product(eligibility)
            and has_create_projects
        )
