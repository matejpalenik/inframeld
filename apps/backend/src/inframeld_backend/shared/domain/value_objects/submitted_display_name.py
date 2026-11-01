import unicodedata
from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class SubmittedDisplayName:
    """Validate only new submissions. Retained legacy labels remain plain strings."""

    value: str

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if (
            not 1 <= len(self.value) <= 128
            or not self.value.strip()
            or self.value != self.value.strip()
            or any(unicodedata.category(c) in {"Cc", "Cs", "Zl", "Zp"} for c in self.value)
        ):
            raise ValueError(
                "A display name requires 1–128 code points without surrounding whitespace or controls."
            )
