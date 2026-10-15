from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class OAuthIssuer:
    """Identify an OAuth issuer using exact text, without URL normalization."""

    value: str

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if not self.value.strip():
            raise ValueError("An OAuth issuer must be nonblank.")
