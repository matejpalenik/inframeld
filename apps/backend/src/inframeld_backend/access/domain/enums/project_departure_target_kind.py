from enum import StrEnum


class ProjectDepartureTargetKind(StrEnum):
    """Identify the resource whose remaining human responsibility must be preserved."""

    PROJECT = "project"
    ACCESS_GROUP = "access_group"
    APPLICATION_ACCOUNT = "application_account"
