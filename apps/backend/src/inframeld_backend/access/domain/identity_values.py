"""Identify an external account by its source and subject, without email matching."""

from dataclasses import dataclass

from inframeld_backend.shared.domain.value_validation import require_string


@dataclass(frozen=True, slots=True)
class IdentityAuthority:
    """Identify the trusted external identity source using exact, nonblank text."""

    value: str

    def __post_init__(self) -> None:
        """Reject an absent identity source without rewriting its case or whitespace."""
        require_string(self.value)
        if not self.value.strip():
            raise ValueError("An identity authority must be nonblank.")


@dataclass(frozen=True, slots=True)
class IdentitySubject:
    """Identify an account within its authority using exact, nonblank provider text."""

    value: str

    def __post_init__(self) -> None:
        """Reject an absent subject without treating email or display name as identity."""
        require_string(self.value)
        if not self.value.strip():
            raise ValueError("An identity subject must be nonblank.")
