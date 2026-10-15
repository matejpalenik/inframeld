from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class IdentityAuthority:
    """Identify the trusted external identity source using exact, nonblank text."""

    value: str

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if not self.value.strip():
            raise ValueError("An identity authority must be nonblank.")
