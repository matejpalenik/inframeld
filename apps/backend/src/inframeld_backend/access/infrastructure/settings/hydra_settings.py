from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator
from pydantic_settings import NoDecode

from inframeld_backend.access.domain.value_objects.human_api_audience import HumanAPIAudience
from inframeld_backend.access.domain.value_objects.oauth_issuer import OAuthIssuer


def _require_endpoint(value: str) -> None:
    message = "Expected an HTTP(S) URL without credentials, query or fragment."

    if not value or any(character.isspace() or ord(character) < 32 for character in value):
        raise ValueError(message)

    try:
        parsed = urlsplit(value)
        _ = parsed.port
    except ValueError:
        raise ValueError(message) from None

    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "?" in value
        or "#" in value
    ):
        raise ValueError(message)


class HydraSettings(BaseModel):
    """Preserve exact issuer / audience identifiers in operator configuration.

    Private container-network HTTP is a deployment concern - these settings do not authorize
    public HTTP exposure or the CLI's managed-local exception."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    admin_url: HttpUrl
    public_url: HttpUrl | None = None
    issuer: Annotated[OAuthIssuer, NoDecode]
    api_audience: Annotated[HumanAPIAudience, NoDecode]
    client_id: Literal["inframeld-cli"] = "inframeld-cli"
    required_scope: Literal["inframeld:api"] = "inframeld:api"
    remember_consent_seconds: int = Field(default=3600, gt=0)

    @field_validator("remember_consent_seconds", mode="before")
    @classmethod
    def _validate_remember_duration(cls, value: object) -> object:
        if isinstance(value, (bool, float)):
            raise ValueError("Remembered consent requires a positive whole duration.")
        return value

    @field_validator("public_url")
    @classmethod
    def _validate_public_url(cls, value: HttpUrl | None) -> HttpUrl | None:
        if value is not None:
            _require_endpoint(str(value))
        return value

    @field_validator("admin_url")
    @classmethod
    def _validate_admin_url(cls, value: HttpUrl) -> HttpUrl:
        _require_endpoint(str(value))
        return value

    @field_validator("issuer", mode="before")
    @classmethod
    def _parse_issuer(cls, value: object) -> OAuthIssuer:
        if isinstance(value, OAuthIssuer):
            _require_endpoint(value.value)
            return value

        if isinstance(value, str):
            _require_endpoint(value)
            return OAuthIssuer(value)

        raise ValueError("The OAuth issuer must be a URL string.")

    @field_validator("api_audience", mode="before")
    @classmethod
    def _parse_api_audience(cls, value: object) -> HumanAPIAudience:
        if isinstance(value, HumanAPIAudience):
            _require_endpoint(value.value)
            return value

        if isinstance(value, str):
            _require_endpoint(value)
            return HumanAPIAudience(value)

        raise ValueError("The API audience must be a URL string.")
