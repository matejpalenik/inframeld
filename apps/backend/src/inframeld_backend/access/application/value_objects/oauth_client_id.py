from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class OAuthClientId:
    """Identify a requesting OAuth client - recognition does not authorize it."""

    value: str

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if not self.value.strip():
            raise ValueError("An OAuth client identifier must be nonblank.")
