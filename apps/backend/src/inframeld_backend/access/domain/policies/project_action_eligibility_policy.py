from inframeld_backend.access.domain.enums.principal_kind import PrincipalKind
from inframeld_backend.access.domain.value_objects.action_id import ActionId

_HUMAN_ONLY_ACTIONS = frozenset(
    {
        "manage-project-members",
        "create-access-groups",
        "create-application-accounts",
        "create-pipelines",
        "create-deployments",
        "manage-upload-defaults",
        "delete-project",
        "manage-budget",
        "manage-trace-policy",
        "delete-trace-history",
        "create-collections",
        "create-sources",
        "create-model-connections",
        "create-processing-profiles",
        "create-embedding-profiles",
    }
)
_SHARED_ACTIONS = frozenset({"inspect-budget", "inspect-feedback"})


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
