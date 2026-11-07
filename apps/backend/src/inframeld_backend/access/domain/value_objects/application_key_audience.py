from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class ApplicationKeyAudience:
    """Identify an exact server-configured application credential resource."""

    value: str

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if not self.value.strip():
            raise ValueError("An application credential audience must be nonblank.")
