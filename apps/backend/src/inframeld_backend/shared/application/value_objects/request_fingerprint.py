from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RequestFingerprint:
    """Carry the immutable 32-byte HMAC digest used to recognize request meaning."""

    value: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.value) is not bytes:
            raise TypeError("Fingerprint must contain immutable bytes.")
        if len(self.value) != 32:
            raise ValueError("Fingerprint must contain exactly 32 bytes.")
