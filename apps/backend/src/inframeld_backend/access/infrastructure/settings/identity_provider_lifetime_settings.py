import re

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class IdentityProviderLifetimeSettings(BaseSettings):
    """Validate the native provider lifetimes shared by startup and setup preflight."""

    model_config = SettingsConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    access_token: str = Field(default="5m", validation_alias="TTL_ACCESS_TOKEN")
    refresh_token: str = Field(default="168h", validation_alias="TTL_REFRESH_TOKEN")
    auth_code: str = Field(default="1m", validation_alias="TTL_AUTH_CODE")
    browser_session: str = Field(default="8h", validation_alias="SESSION_LIFESPAN")

    @field_validator("access_token", "refresh_token", "auth_code", "browser_session")
    @classmethod
    def _require_positive_duration(cls, value: str) -> str:
        message = "Provider lifetimes require a positive finite duration within signed 64-bit nanoseconds."
        if re.fullmatch(r"(?:[0-9]+(?:ns|us|ms|s|m|h))+", value) is None:
            raise ValueError(message)
        units = {
            "ns": 1,
            "us": 1000,
            "ms": 1000000,
            "s": 1000000000,
            "m": 60000000000,
            "h": 3600000000000,
        }
        total = sum(
            int(amount) * units[unit]
            for amount, unit in re.findall(r"([0-9]+)(ns|us|ms|s|m|h)", value)
        )
        if not 0 < total <= 2**63 - 1:
            raise ValueError(message)
        return value
