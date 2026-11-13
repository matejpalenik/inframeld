from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class ModelConnectionId:
    """Identify one Model Connection independently of its current access configuration."""

    value: UUID

    def __post_init__(self) -> None:
        ValueValidation.require_uuid(self.value)
