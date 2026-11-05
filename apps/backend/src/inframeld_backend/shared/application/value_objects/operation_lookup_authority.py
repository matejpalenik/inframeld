from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError

_PROJECT_ACTIONS = frozenset(
    {
        "edit-project-metadata",
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
        parts = requested_route.split("/")
        grant_path = (
            len(parts) >= 5 and parts[:3] == ["", "v1", "projects"] and parts[4] == "grants"
        )
        if grant_path or self.family is family.PROJECT_GRANT_READ:
            legacy = (
                requested_route == _GRANT_ROUTE
                and method == "POST"
                and project_id is not None
                and self.family is family.PROJECT_GRANT_READ
                and self.action_id.value == "create-access-groups"
            )
            management = False
            if (
                len(parts) == 7
                and method in {"PUT", "DELETE"}
                and project_id is not None
                and self.family is family.PROJECT_GRANT_READ
                and self.action_id.value in _PROJECT_ACTIONS
                and parts[6] == self.action_id.value
            ):
                try:
                    management = (
                        UUID(parts[3]) == project_id.value
                        and str(project_id.value) == parts[3]
                        and str(UUID(parts[5])) == parts[5]
                    )
                except ValueError:
                    management = False
            if not legacy and not management:
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
