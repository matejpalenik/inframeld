from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId

_HUMAN_ONLY_ACTIONS = frozenset(
    {
        ProjectAction.EDIT_PROJECT_METADATA.value,
        ProjectAction.MANAGE_PROJECT_MEMBERS.value,
        ProjectAction.CREATE_ACCESS_GROUPS.value,
        ProjectAction.CREATE_APPLICATION_ACCOUNTS.value,
        ProjectAction.CREATE_PIPELINES.value,
        ProjectAction.CREATE_DEPLOYMENTS.value,
        ProjectAction.MANAGE_UPLOAD_DEFAULTS.value,
        ProjectAction.DELETE_PROJECT.value,
        ProjectAction.MANAGE_BUDGET.value,
        ProjectAction.MANAGE_TRACE_POLICY.value,
        ProjectAction.DELETE_TRACE_HISTORY.value,
        ProjectAction.CREATE_COLLECTIONS.value,
        ProjectAction.CREATE_SOURCES.value,
        ProjectAction.CREATE_MODEL_CONNECTIONS.value,
        ProjectAction.CREATE_PROCESSING_PROFILES.value,
        ProjectAction.CREATE_EMBEDDING_PROFILES.value,
    }
)
_SHARED_ACTIONS = frozenset(
    {ProjectAction.INSPECT_BUDGET.value, ProjectAction.INSPECT_FEEDBACK.value}
)


class ProjectActionEligibilityPolicy:
    """Limit Project authority to catalogue actions eligible for the caller kind.

    An exact stored grant cannot enable a human-only action for an application
    or give a Project authority meaning that belongs to another target.
    """

    @staticmethod
    def may_use(*, action_id: ActionId, principal_kind: PrincipalKind) -> bool:
        return action_id.value in _SHARED_ACTIONS or (
            principal_kind is PrincipalKind.HUMAN and action_id.value in _HUMAN_ONLY_ACTIONS
        )
