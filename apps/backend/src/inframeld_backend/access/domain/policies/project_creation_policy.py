from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.policies.principal_access_policy import PrincipalAccessPolicy
from inframeld_backend.access.domain.policy_inputs.principal_access_policy_input import (
    PrincipalAccessPolicyInput,
)


class ProjectCreationPolicy:
    INITIAL_ACTIONS = (
        ProjectAction.MANAGE_PROJECT_MEMBERS.value,
        ProjectAction.CREATE_ACCESS_GROUPS.value,
        ProjectAction.CREATE_APPLICATION_ACCOUNTS.value,
        ProjectAction.CREATE_PIPELINES.value,
        ProjectAction.CREATE_DEPLOYMENTS.value,
        ProjectAction.MANAGE_UPLOAD_DEFAULTS.value,
        ProjectAction.DELETE_PROJECT.value,
        ProjectAction.INSPECT_BUDGET.value,
        ProjectAction.MANAGE_BUDGET.value,
        ProjectAction.MANAGE_TRACE_POLICY.value,
        ProjectAction.DELETE_TRACE_HISTORY.value,
        ProjectAction.INSPECT_FEEDBACK.value,
        ProjectAction.CREATE_COLLECTIONS.value,
        ProjectAction.CREATE_SOURCES.value,
        ProjectAction.CREATE_MODEL_CONNECTIONS.value,
        ProjectAction.CREATE_PROCESSING_PROFILES.value,
        ProjectAction.CREATE_EMBEDDING_PROFILES.value,
        ProjectAction.EDIT_PROJECT_METADATA.value,
    )

    @staticmethod
    def may_create(eligibility: PrincipalAccessPolicyInput, *, has_create_projects: bool) -> bool:
        return (
            eligibility.principal.kind is PrincipalKind.HUMAN
            and PrincipalAccessPolicy.may_use_product(eligibility)
            and has_create_projects
        )
