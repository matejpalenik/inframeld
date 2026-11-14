from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EncryptedProviderCredentialDTO:
    """Carry the complete stored envelope without rendering its encrypted bytes."""

    format_version: int
    algorithm: str
    key_id: str
    message: bytes = field(repr=False)
