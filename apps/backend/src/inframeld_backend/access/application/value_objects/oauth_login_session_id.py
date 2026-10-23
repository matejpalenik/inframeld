from dataclasses import dataclass
from uuid import UUID

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class OAuthLoginSessionId:
    """Identify one remembered Hydra login, independently of its token grants."""

    value: UUID

    def __post_init__(self) -> None:
        ValueValidation.require_uuid(self.value)
