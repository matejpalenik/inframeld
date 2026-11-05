from enum import StrEnum


class ProjectActionGrantChangeKind(StrEnum):
    """Retain whether an exact Project action grant was set or removed."""

    SET = "set"
    REMOVE = "remove"
