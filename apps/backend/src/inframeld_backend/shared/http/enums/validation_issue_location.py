from enum import StrEnum


class ValidationIssueLocation(StrEnum):
    """Identify the request component that contains an invalid field."""

    BODY = "body"
    PATH = "path"
    QUERY = "query"
    HEADER = "header"
    COOKIE = "cookie"
    REQUEST = "request"
