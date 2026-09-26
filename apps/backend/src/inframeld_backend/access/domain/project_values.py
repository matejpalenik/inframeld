"""Define the project values owned by Access."""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from inframeld_backend.shared.domain.value_validation import require_uuid


@dataclass(frozen=True, slots=True)
class ProjectId:
    """Identify one Project using a UUID, independently of its existence."""

    value: UUID

    def __post_init__(self) -> None:
        """Require parsing at the boundary before creating a nominal identifier."""
        require_uuid(self.value)


class ProjectStatus(StrEnum):
    """Distinguish usable projects from projects undergoing deletion."""

    ACTIVE = "active"
    DELETING = "deleting"
