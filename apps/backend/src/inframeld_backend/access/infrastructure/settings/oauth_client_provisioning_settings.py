from typing import Annotated

from pydantic import Field, FiniteFloat
from pydantic_settings import BaseSettings, SettingsConfigDict

from inframeld_backend.access.infrastructure.settings.hydra_settings import HydraSettings
from inframeld_backend.access.infrastructure.settings.identity_provider_lifetime_settings import (
    IdentityProviderLifetimeSettings,
)


class OAuthClientProvisioningSettings(BaseSettings):
    """Read only provider configuration - setup needs no application database or HMAC key."""

    model_config = SettingsConfigDict(
        env_prefix="INFRAMELD_",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    hydra: HydraSettings
    lifetimes: IdentityProviderLifetimeSettings = Field(
        default_factory=IdentityProviderLifetimeSettings
    )
    readiness_timeout_seconds: Annotated[FiniteFloat, Field(gt=0)] = Field(
        default=60, validation_alias="INFRAMELD_OAUTH_PROVISIONING__READINESS_TIMEOUT_SECONDS"
    )
    timeout_seconds: Annotated[FiniteFloat, Field(gt=0)] = Field(
        default=10, validation_alias="INFRAMELD_OAUTH_PROVISIONING__TIMEOUT_SECONDS"
    )
