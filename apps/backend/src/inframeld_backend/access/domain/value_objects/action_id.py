from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import require_string


@dataclass(frozen=True, slots=True)
class ActionId:
    """Name one exact action using nonblank text that fits the persisted 100-character vocabulary."""

    value: str

    def __post_init__(self) -> None:
        require_string(self.value)
        if not self.value.strip() or len(self.value) > 100:
            raise ValueError("An action ID must be nonblank and at most 100 characters.")
