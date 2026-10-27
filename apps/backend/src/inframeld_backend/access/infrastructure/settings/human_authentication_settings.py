"""Validate the time allowed for one human authentication attempt."""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HumanAuthenticationSettings(BaseModel):
    """Share provider and total limits between cookie and bearer authentication.

    The total limit includes provider verification and the local principal read.
    A shorter total limit also shortens the allowed provider wait.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    provider_timeout_seconds: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    total_timeout_seconds: float = Field(default=10.0, gt=0, allow_inf_nan=False)

    @field_validator("provider_timeout_seconds", "total_timeout_seconds", mode="before")
    @classmethod
    def _reject_boolean_timeout(cls, value: object) -> object:
        # Reject booleans before numeric parsing could turn True into 1.0.
        if isinstance(value, bool):
            raise ValueError("Authentication timeouts must be finite and positive numbers.")
        return value
