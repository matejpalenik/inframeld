import base64
import hashlib
import re
import secrets
from dataclasses import dataclass, field
from typing import Self
from uuid import UUID, uuid4

from inframeld_backend.access.domain.value_objects.application_key_id import ApplicationKeyId
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation

_KEY = re.compile(
    r"ifm_app_([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})_([A-Za-z0-9_-]{43})"
)


@dataclass(frozen=True, slots=True)
class ApplicationKeyCredential:
    """Carry a complete key through first delivery or verification without rendering it."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        match = _KEY.fullmatch(self.value)
        if match is None:
            raise ValueError("The application credential is not canonical.")

        secret = match.group(2)
        decoded = base64.urlsafe_b64decode(secret + "=")
        if len(decoded) != 32 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != secret:
            raise ValueError("The application credential is not canonical.")

    @property
    def key_id(self) -> ApplicationKeyId:
        return ApplicationKeyId(UUID(self.value[8:44]))

    @classmethod
    def generate(cls) -> Self:
        """Allocate a UUIDv4 lookup ID and 32 cryptographically random secret bytes."""
        secret = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")
        return cls(f"ifm_app_{uuid4()}_{secret}")

    def digest(self) -> bytes:
        """Retain only the complete canonical key's SHA-256 verifier."""
        return hashlib.sha256(self.value.encode("ascii")).digest()
