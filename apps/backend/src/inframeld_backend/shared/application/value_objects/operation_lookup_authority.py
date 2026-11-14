from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.access.domain.enums.access_group_action import AccessGroupAction
from inframeld_backend.access.domain.enums.application_account_action import (
    ApplicationAccountAction,
)
from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.domain.enums.organization_action import OrganizationAction
from inframeld_backend.access.domain.enums.project_action import ProjectAction
from inframeld_backend.access.domain.value_objects.action_id import ActionId
from inframeld_backend.access.domain.value_objects.organization_id import OrganizationId
from inframeld_backend.access.domain.value_objects.project_id import ProjectId
from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)
from inframeld_backend.shared.application.errors.application_errors import InvalidInputError

_PROJECT_ACTIONS = frozenset(
    {
        ProjectAction.EDIT_PROJECT_METADATA.value,
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
    }
)
_ORGANIZATION_ACTIONS = frozenset(
    {
        OrganizationAction.ADMIT_USERS.value,
        OrganizationAction.SUSPEND_USERS.value,
        OrganizationAction.RESTORE_USERS.value,
        OrganizationAction.CREATE_PROJECTS.value,
    }
)
_GRANT_ROUTE = "/v1/projects/{project_id}/grants"


@dataclass(frozen=True, slots=True)
class OperationLookupAuthority:
    """Describe original authority meaning, never current permission."""

    family: OperationLookupAuthorityFamily
    action_id: ActionId

    def require_supported_scope(
        self,
        *,
        project_id: ProjectId | None,
        method: str,
        requested_route: str,
        organization_id: OrganizationId | None = None,
    ) -> None:
        """Reject invented target/action combinations and fixed-route downgrades."""
        if method not in {"POST", "PUT", "PATCH", "DELETE"} or not requested_route.strip():
            raise InvalidInputError()

        family = OperationLookupAuthorityFamily
        parts = requested_route.split("/")
        organization_grant_path = (
            len(parts) >= 5 and parts[:3] == ["", "v1", "organizations"] and parts[4] == "grants"
        )
        if organization_grant_path or self.family is family.ORGANIZATION_GRANT_READ:
            valid = False
            if (
                len(parts) == 7
                and parts[:3] == ["", "v1", "organizations"]
                and parts[4] == "grants"
                and organization_id is not None
                and project_id is None
                and method in {"PUT", "DELETE"}
                and self.family is family.ORGANIZATION_GRANT_READ
                and self.action_id.value in _ORGANIZATION_ACTIONS
                and parts[3] == str(organization_id.value)
                and parts[6] == self.action_id.value
            ):
                try:
                    valid = str(UUID(parts[5])) == parts[5]
                except ValueError:
                    valid = False
            if not valid:
                raise InvalidInputError()
            return

        model_grant_path = (
            len(parts) >= 5
            and parts[:3] == ["", "v1", "model-connections"]
            and parts[4] == "grants"
        )
        if model_grant_path or self.family is family.MODEL_CONNECTION_GRANT_READ:
            valid = False
            if (
                model_grant_path
                and len(parts) == 7
                and project_id is not None
                and self.family is family.MODEL_CONNECTION_GRANT_READ
                and method in {"PUT", "DELETE"}
                and self.action_id.value in ModelConnectionAction
                and parts[6] == self.action_id.value
            ):
                try:
                    valid = str(UUID(parts[3])) == parts[3] and str(UUID(parts[5])) == parts[5]
                except ValueError:
                    valid = False
            if not valid:
                raise InvalidInputError()
            return

        scoped_grant_path = (
            len(parts) >= 7 and parts[:3] == ["", "v1", "projects"] and parts[6] == "grants"
        )
        if scoped_grant_path or self.family in {
            family.ACCESS_GROUP_GRANT_READ,
            family.APPLICATION_ACCOUNT_GRANT_READ,
        }:
            target, actions = (
                ("access-groups", frozenset(AccessGroupAction))
                if self.family is family.ACCESS_GROUP_GRANT_READ
                else ("application-accounts", frozenset(ApplicationAccountAction))
            )
            valid = False
            if (
                len(parts) == 9
                and parts[:3] == ["", "v1", "projects"]
                and parts[4] == target
                and parts[6] == "grants"
                and project_id is not None
                and parts[3] == str(project_id.value)
                and self.family
                in {family.ACCESS_GROUP_GRANT_READ, family.APPLICATION_ACCOUNT_GRANT_READ}
                and method in {"PUT", "DELETE"}
                and self.action_id.value in actions
                and parts[8] == self.action_id.value
            ):
                try:
                    valid = str(UUID(parts[5])) == parts[5] and str(UUID(parts[7])) == parts[7]
                except ValueError:
                    valid = False
            if not valid:
                raise InvalidInputError()
            return

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

        if self.family is family.PROJECT_DELETION:
            if (
                project_id is None
                or method != "DELETE"
                or self.action_id.value != "delete-project"
                or requested_route != f"/v1/projects/{project_id.value}"
            ):
                raise InvalidInputError()
            return

        if self.family is family.ACCESS_GROUP_DELETION:
            valid = False
            if (
                project_id is not None
                and method == "DELETE"
                and self.action_id.value == "delete-access-group"
                and len(parts) == 6
                and parts[:3] == ["", "v1", "projects"]
                and parts[4] == "access-groups"
            ):
                try:
                    valid = parts[3] == str(project_id.value) and parts[5] == str(UUID(parts[5]))
                except ValueError:
                    valid = False
            if not valid:
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
