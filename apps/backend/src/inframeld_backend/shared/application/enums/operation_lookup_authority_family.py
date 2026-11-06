from enum import StrEnum


class OperationLookupAuthorityFamily(StrEnum):
    """Select a fixed current-authority check without granting permission."""

    PROJECT_ACTION_USE = "project_action_use"
    PROJECT_GRANT_READ = "project_grant_read"
    ORGANIZATION_ACTION_USE = "organization_action_use"
    ORGANIZATION_GRANT_READ = "organization_grant_read"
    ACCESS_GROUP_GRANT_READ = "access_group_grant_read"
    APPLICATION_ACCOUNT_GRANT_READ = "application_account_grant_read"
    ACCESS_GROUP_DELETION = "access_group_deletion"
