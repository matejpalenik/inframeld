from enum import StrEnum


class OrganizationAction(StrEnum):
    """Name an action on the installation Organization."""

    ADMIT_USERS = "admit-users"
    SUSPEND_USERS = "suspend-users"
    RESTORE_USERS = "restore-users"
    CREATE_PROJECTS = "create-projects"
