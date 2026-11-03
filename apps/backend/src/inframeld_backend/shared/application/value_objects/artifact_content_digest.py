import hashlib
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ArtifactContentDigest:
    """Identify complete content with authoritative SHA-256 bytes, never an S3 ETag."""

    value: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.value) is not bytes:
            raise TypeError("A content digest requires SHA-256 bytes.")
        if len(self.value) != 32:
            raise ValueError("A SHA-256 content digest must contain exactly 32 bytes.")

    @staticmethod
    def from_content(content: bytes) -> "ArtifactContentDigest":
        return ArtifactContentDigest(hashlib.sha256(content).digest())
