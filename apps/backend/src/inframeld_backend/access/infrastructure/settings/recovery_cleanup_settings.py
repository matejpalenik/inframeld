from typing import Annotated, Self
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from pydantic_settings import NoDecode

from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority


class RecoveryCleanupSettings(BaseModel):
    """Configure only the resources and bounds needed by background recovery."""

    model_config = ConfigDict(
        frozen=True, extra="forbid", hide_input_in_errors=True, allow_inf_nan=False
    )

    authority: Annotated[IdentityAuthority, NoDecode]
    hydra_admin_url: HttpUrl
    poll_seconds: float = Field(default=1, gt=0, le=30)
    provider_timeout_seconds: float = Field(default=5, gt=0, le=30)
    database_timeout_seconds: float = Field(default=5, gt=0, le=30)
    lease_seconds: float = Field(default=60, gt=0, le=300)
    shutdown_seconds: float = Field(default=15, gt=0, le=60)

    @field_validator("authority", mode="before")
    @classmethod
    def _authority(cls, value: object) -> IdentityAuthority:
        if isinstance(value, IdentityAuthority):
            return value
        if isinstance(value, str):
            return IdentityAuthority(value)
        raise ValueError("A provider authority is required.")

    @field_validator(
        "poll_seconds",
        "provider_timeout_seconds",
        "database_timeout_seconds",
        "lease_seconds",
        "shutdown_seconds",
        mode="before",
    )
    @classmethod
    def _no_boolean_deadlines(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("A deadline cannot be a boolean.")
        return value

    @model_validator(mode="after")
    def _consistent_bounds(self) -> Self:
        if (
            self.lease_seconds
            < 2 * self.provider_timeout_seconds + 6 * self.database_timeout_seconds + 5
        ):
            raise ValueError("The lease must cover both calls and bounded checkpoints.")
        if self.shutdown_seconds < self.provider_timeout_seconds + self.database_timeout_seconds:
            raise ValueError("Shutdown must allow the current call and checkpoint to finish.")
        return self

    @field_validator("hydra_admin_url")
    @classmethod
    def _require_private_endpoint_shape(cls, value: HttpUrl) -> HttpUrl:
        parsed = urlsplit(str(value))
        if (
            parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("The provider endpoint cannot contain credentials, query or fragment.")
        return value
