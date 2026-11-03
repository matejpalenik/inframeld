import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ArtifactStorageSettings(BaseSettings):
    """Configure explicit private storage and finite calls without ambient credentials."""

    endpoint_url: str
    bucket: str
    access_key_id: SecretStr = Field(min_length=1, repr=False)
    secret_access_key: SecretStr = Field(min_length=1, repr=False)
    region: str = Field(default="us-east-1", min_length=1)
    ca_bundle: Path | None = None
    addressing_style: Literal["path", "virtual"] = "path"
    connect_timeout_seconds: float = Field(default=5, gt=0, le=30)
    read_timeout_seconds: float = Field(default=30, gt=0, le=30)
    operation_timeout_seconds: float = Field(default=30, gt=0, le=30)
    max_object_bytes: int = Field(default=256 * 1024 * 1024, gt=0, le=256 * 1024 * 1024)
    list_page_size: int = Field(default=100, ge=1, le=1000)

    model_config = SettingsConfigDict(
        env_prefix="INFRAMELD_ARTIFACT_STORAGE__",
        extra="ignore",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )

    @field_validator("endpoint_url")
    @classmethod
    def require_explicit_endpoint(cls, value: str) -> str:
        endpoint = urlsplit(value)
        if (
            endpoint.scheme not in ("http", "https")
            or not endpoint.hostname
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError(
                "A storage endpoint requires an explicit HTTP(S) host without credentials."
            )
        return value

    @field_validator("bucket")
    @classmethod
    def require_private_bucket_name(cls, value: str) -> str:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", value) or ".." in value:
            raise ValueError("The private storage bucket name is invalid.")
        return value

    @field_validator("ca_bundle")
    @classmethod
    def require_absolute_path(cls, value: Path | None) -> Path | None:
        if value is not None and not value.is_absolute():
            raise ValueError("Storage paths must be absolute operator-owned paths.")
        return value
