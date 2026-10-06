"""Validate the deployment identity authority and Kratos public API location."""

from typing import Annotated
from urllib.parse import urlsplit

from pydantic import BaseModel, HttpUrl, field_validator
from pydantic_settings import NoDecode

from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority


class KratosSettings(BaseModel):
    """Keep the admin endpoint explicit when human bearer verification is configured.

    Cookie-only deployments only need the public URL and identity authority.
    Deployment networking owns whether an endpoint is private and uses TLS.
    """

    public_url: HttpUrl
    authority: Annotated[IdentityAuthority, NoDecode]
    admin_url: HttpUrl | None = None

    @field_validator("admin_url", mode="before")
    @classmethod
    def _validate_admin_url(cls, value: object) -> object:
        if value is None:
            return None

        message = "The Kratos admin URL must be HTTP(S) without credentials, query or fragments."

        if not isinstance(value, (str, HttpUrl)):
            raise ValueError(message)

        endpoint = str(value)

        if not endpoint or any(
            character.isspace() or ord(character) < 32 for character in endpoint
        ):
            raise ValueError(message)

        try:
            parsed = urlsplit(endpoint)
            _ = parsed.port
        except ValueError:
            raise ValueError(message) from None

        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or "?" in endpoint
            or "#" in endpoint
        ):
            raise ValueError(message)

        return value

    @field_validator("authority", mode="before")
    @classmethod
    def _parse_authority(cls, value: object) -> IdentityAuthority:
        """Convert a configured identity-source string to its validated application value."""
        if isinstance(value, IdentityAuthority):
            return value
        if isinstance(value, str):
            return IdentityAuthority(value)
        raise ValueError("The Kratos authority must be a string.")
