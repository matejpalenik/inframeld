"""Validate the deployment identity authority and Kratos public API location."""

from typing import Annotated

from pydantic import BaseModel, HttpUrl, field_validator
from pydantic_settings import NoDecode

from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority


class KratosSettings(BaseModel):
    """Configure the trusted Kratos endpoint and its application-owned identity authority."""

    public_url: HttpUrl
    authority: Annotated[IdentityAuthority, NoDecode]

    @field_validator("authority", mode="before")
    @classmethod
    def _parse_authority(cls, value: object) -> IdentityAuthority:
        """Convert a configured identity-source string to its validated application value."""
        if isinstance(value, IdentityAuthority):
            return value
        if isinstance(value, str):
            return IdentityAuthority(value)
        raise ValueError("The Kratos authority must be a string.")
