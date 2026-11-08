import base64
import hashlib
import re
import secrets
from dataclasses import dataclass, field
from typing import Self

from inframeld_backend.access.domain.value_objects.invitation_token_digest import (
    InvitationTokenDigest,
)
from inframeld_backend.shared.domain.validation.value_validation import ValueValidation


@dataclass(frozen=True, slots=True)
class InvitationToken:
    """Carry a show-once invitation secret without exposing it in representations."""

    value: str = field(repr=False)

    def __post_init__(self) -> None:
        ValueValidation.require_string(self.value)
        if re.fullmatch(r"[A-Za-z0-9_-]{43}", self.value) is None:
            raise ValueError("An invitation token requires 43 unpadded base64url characters.")

        raw = base64.urlsafe_b64decode(self.value + "=")
        if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != self.value:
            raise ValueError("An invitation token requires canonical base64url encoding.")

    @classmethod
    def generate(cls) -> Self:
        return cls(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("="))

    def digest(self) -> InvitationTokenDigest:
        return InvitationTokenDigest(hashlib.sha256(self.value.encode("ascii")).digest())
