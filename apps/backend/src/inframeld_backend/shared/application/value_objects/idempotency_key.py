from dataclasses import dataclass

from inframeld_backend.shared.domain.validation.value_validation import require_string


@dataclass(frozen=True, slots=True)
class IdempotencyKey:
    """Identify the caller's opaque retry key."""

    value: str

    def __post_init__(self) -> None:
        require_string(self.value)

        if not self.value.strip() or len(self.value) > 128:
            raise ValueError("Idempotency key must be nonblank and at most 128 characters.")
