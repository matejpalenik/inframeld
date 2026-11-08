import hmac
from dataclasses import dataclass, field
from typing import Self


@dataclass(frozen=True, slots=True)
class InvitationTokenDigest:
    """Retain token verification material without retaining the delivered secret."""

    value: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.value) is not bytes:
            raise TypeError("An invitation digest requires immutable bytes.")
        if len(self.value) != 32:
            raise ValueError("An invitation digest requires exactly 32 bytes.")

    def matches(self, candidate: Self) -> bool:
        """Compare same-sized verification material without a prefix-dependent comparison."""
        return hmac.compare_digest(self.value, candidate.value)
