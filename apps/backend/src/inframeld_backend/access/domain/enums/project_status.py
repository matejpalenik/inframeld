from enum import StrEnum


class ProjectStatus(StrEnum):
    """Distinguish usable projects from projects undergoing deletion."""

    ACTIVE = "active"
    DELETING = "deleting"
