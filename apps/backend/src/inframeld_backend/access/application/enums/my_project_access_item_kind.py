from enum import StrEnum


class MyProjectAccessItemKind(StrEnum):
    """Identify one grant or group relationship in a combined own-access page."""

    GRANT = "grant"
    MEMBERSHIP = "membership"
    MANAGEMENT = "management"
