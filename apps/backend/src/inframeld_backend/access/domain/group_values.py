"""Define the group values owned by Access."""

from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.shared.domain.value_validation import require_uuid


@dataclass(frozen=True, slots=True)
class AccessGroupId:
    """Identify one AccessGroup using a UUID, independently of its existence."""

    value: UUID

    def __post_init__(self) -> None:
        """Require parsing at the boundary before creating a nominal identifier."""
        require_uuid(self.value)
