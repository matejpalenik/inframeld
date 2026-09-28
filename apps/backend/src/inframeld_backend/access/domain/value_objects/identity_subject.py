from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import require_string


@dataclass(frozen=True, slots=True)
class IdentitySubject:
    """Identify an account within its authority using exact, nonblank provider text."""

    value: str

    def __post_init__(self) -> None:
        require_string(self.value)
        if not self.value.strip():
            raise ValueError("An identity subject must be nonblank.")
