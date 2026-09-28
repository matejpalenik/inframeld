"""Locate the separately protected idempotency fingerprint HMAC key."""

from pathlib import Path

from pydantic import BaseModel, field_validator


class RequestFingerprintSettings(BaseModel):
    """Configure the key's location without placing its bytes in settings."""

    key_file: Path

    @field_validator("key_file")
    @classmethod
    def require_absolute_key_file(cls, value: Path) -> Path:
        if not value.is_absolute():
            raise ValueError("Fingerprint key file path must be absolute.")
        return value
