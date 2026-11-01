from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.shared.application.value_objects.deletion_status_retention_profile import (
    DeletionStatusRetentionProfile,
)


class DeletionStatusRetentionSettings(BaseModel):
    """Capture operator-reviewed installation policy for future original-request bindings."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)

    days: int = Field(default=30, ge=1, le=90)

    @field_validator("days", mode="before")
    @classmethod
    def _require_whole_days(cls, value: object) -> int:
        if type(value) is int:
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
        raise ValueError("Status retention requires a whole number of days.")

    def to_profile(self) -> DeletionStatusRetentionProfile:
        return DeletionStatusRetentionProfile(days=self.days)
