from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_MAXIMUM_LIFETIME_SECONDS = 30 * 24 * 60 * 60


class InvitationSettings(BaseModel):
    """Bound operator invitation lifetimes without configuring identity providers."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    default_lifetime_seconds: int = Field(
        default=7 * 24 * 60 * 60, gt=0, le=_MAXIMUM_LIFETIME_SECONDS
    )
    maximum_lifetime_seconds: int = Field(
        default=_MAXIMUM_LIFETIME_SECONDS, gt=0, le=_MAXIMUM_LIFETIME_SECONDS
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
        raise ValueError("Invitation lifetimes require whole seconds.")

    @model_validator(mode="after")
    def _require_default_within_maximum(self) -> Self:
        if self.default_lifetime_seconds > self.maximum_lifetime_seconds:
            raise ValueError("The default invitation lifetime must not exceed its maximum.")
        return self
