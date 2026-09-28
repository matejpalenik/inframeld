"""Carry the separately protected key used for idempotency fingerprints."""

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RequestFingerprintKey:
    """Keep fingerprint key material out of representations and error messages."""

    value: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.value) is not bytes or len(self.value) < 32:
            raise ValueError("A fingerprint key must contain at least 32 bytes.")
