from dataclasses import dataclass

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError

_PROJECT_ACTIONS = frozenset(
    {
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
    }
)
_ORGANIZATION_ACTIONS = frozenset(
    {"admit-users", "suspend-users", "restore-users", "create-projects"}
)
_GRANT_ROUTE = "/v1/projects/{project_id}/grants"


@dataclass(frozen=True, slots=True)
class OperationLookupAuthority:
    """Describe original authority meaning, never current permission."""

    family: OperationLookupAuthorityFamily
    action_id: ActionId

    def require_supported_scope(
        self, *, project_id: ProjectId | None, method: str, requested_route: str
    ) -> None:
        """Reject invented target/action combinations and fixed-route downgrades."""
        if method not in {"POST", "PUT", "PATCH", "DELETE"} or not requested_route.strip():
            raise InvalidInputError()

        family = OperationLookupAuthorityFamily
        if requested_route == _GRANT_ROUTE or self.family is family.PROJECT_GRANT_READ:
            if not (
                requested_route == _GRANT_ROUTE
                and method == "POST"
                and project_id is not None
                and self.family is family.PROJECT_GRANT_READ
                and self.action_id.value == "create-access-groups"
            ):
                raise InvalidInputError()
            return

        if self.family is family.PROJECT_ACTION_USE:
            valid = project_id is not None and self.action_id.value in _PROJECT_ACTIONS
        elif self.family is family.ORGANIZATION_ACTION_USE:
            valid = project_id is None and self.action_id.value in _ORGANIZATION_ACTIONS
        else:
            valid = False
        if not valid:
            raise InvalidInputError()
