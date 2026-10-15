from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class HumanAPIAudience:
    """Identify the intended human-token API using exact audience text."""

    value: str

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)

        if not self.value.strip():
            raise ValueError("A human API audience must be nonblank.")
