from enum import StrEnum


class ProjectAction(StrEnum):
    """Name an action on a Project without granting it to the caller."""

    MANAGE_PROJECT_MEMBERS = "manage-project-members"
    CREATE_ACCESS_GROUPS = "create-access-groups"
    CREATE_APPLICATION_ACCOUNTS = "create-application-accounts"
    CREATE_PIPELINES = "create-pipelines"
    CREATE_DEPLOYMENTS = "create-deployments"
    MANAGE_UPLOAD_DEFAULTS = "manage-upload-defaults"
    DELETE_PROJECT = "delete-project"
    INSPECT_BUDGET = "inspect-budget"
    MANAGE_BUDGET = "manage-budget"
    MANAGE_TRACE_POLICY = "manage-trace-policy"
    DELETE_TRACE_HISTORY = "delete-trace-history"
    INSPECT_FEEDBACK = "inspect-feedback"
    CREATE_COLLECTIONS = "create-collections"
    CREATE_SOURCES = "create-sources"
    CREATE_MODEL_CONNECTIONS = "create-model-connections"
    CREATE_PROCESSING_PROFILES = "create-processing-profiles"
    CREATE_EMBEDDING_PROFILES = "create-embedding-profiles"
    EDIT_PROJECT_METADATA = "edit-project-metadata"
