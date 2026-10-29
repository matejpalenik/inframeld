from enum import StrEnum


class OperationLookupAuthorityFamily(StrEnum):
    """Select a fixed current-authority check without granting permission."""

    PROJECT_ACTION_USE = "project_action_use"
    PROJECT_GRANT_READ = "project_grant_read"
    ORGANIZATION_ACTION_USE = "organization_action_use"
