from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.shared.domain.validation.value_validation import require_uuid


@dataclass(frozen=True, slots=True)
class IdentityRecoveryFlowId:
    """Identify the original recovery flow, including retries of its callbacks."""

    value: UUID

    def __post_init__(self) -> None:
        require_uuid(self.value)
