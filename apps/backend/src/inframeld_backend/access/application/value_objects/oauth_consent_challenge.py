from dataclasses import dataclass, field

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class OAuthConsentChallenge:
    """Carry Hydra's opaque consent state without exposing it in representations."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if not self.value or any(
            character.isspace() or ord(character) < 32 for character in self.value
        ):
            raise ValueError("A consent challenge must be nonempty and contain no whitespace.")
