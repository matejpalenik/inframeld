from enum import StrEnum


class GrantTargetKind(StrEnum):
    """Discriminate published grant targets without changing their wire tags."""

    PROJECT = "project"
    ACCESS_GROUP = "access-group"
    APPLICATION_ACCOUNT = "application-account"
