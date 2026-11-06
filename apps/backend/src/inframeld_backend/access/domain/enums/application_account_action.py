from enum import StrEnum


class ApplicationAccountAction(StrEnum):
    """Identify separate human administration actions on one application account."""

    ISSUE_KEYS = "issue-application-keys"
    REVOKE_KEYS = "revoke-application-keys"
    DELETE_ACCOUNT = "delete-application-account"
