"""Carry an opaque browser credential only as far as the verification adapter."""

from dataclasses import dataclass, field

from inframeld_backend.shared.domain.value_validation import require_string


@dataclass(frozen=True, slots=True)
class BrowserSessionCredential:
    """Hold an untrusted session secret, excluding its contents from representations."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        """Reject absent credentials without echoing their secret contents."""
        require_string(self.value)
        if not self.value:
            raise ValueError("A session credential must be nonempty.")
