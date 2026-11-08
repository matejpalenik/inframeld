from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from inframeld_backend.access.domain.policies.application_key_lifetime_policy import (
    ApplicationKeyLifetimePolicy,
)


class ApplicationKeyIssuanceSettings(BaseModel):
    """Configure incoming-key lifetimes independently of identity providers."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    default_lifetime_seconds: int = Field(
        default=90 * 24 * 60 * 60, gt=0, le=ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS
    )
    maximum_lifetime_seconds: int = Field(
        default=365 * 24 * 60 * 60, gt=0, le=ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS
    )

    @field_validator("default_lifetime_seconds", "maximum_lifetime_seconds", mode="before")
    @classmethod
    def _require_whole_seconds(cls, value: object) -> int:
        if type(value) is int:
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
        raise ValueError("Application-key lifetimes require whole seconds.")

    @model_validator(mode="after")
    def _require_default_within_maximum(self) -> Self:
        if self.default_lifetime_seconds > self.maximum_lifetime_seconds:
            raise ValueError("The default application-key lifetime must not exceed its maximum.")
        return self
