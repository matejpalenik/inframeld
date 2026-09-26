"""Identify one server-generated request for correlation across boundaries."""

from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.shared.domain.value_validation import require_uuid


@dataclass(frozen=True, slots=True)
class RequestId:
    """Carry a request UUID independently of actor identity or authorization."""

    value: UUID

    def __post_init__(self) -> None:
        """Reject an unparsed or invalid value at construction."""
        require_uuid(self.value)
