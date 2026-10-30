from typing import Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class JobSettings(BaseSettings):
    """Bound ordinary work independently of the dedicated recovery attempt."""

    capacity: int = Field(default=8, ge=1, le=8)
    lease_seconds: float = Field(default=30, gt=0, le=120)
    poll_seconds: float = Field(default=1, gt=0, le=30)
    database_timeout_seconds: float = Field(default=5, gt=0, le=5)
    shutdown_seconds: float = Field(default=15, gt=0, le=30)
    work_seconds: float = Field(default=7200, gt=0, le=7200)
    queue_wait_seconds: float = Field(default=86400, gt=0, le=86400)

    model_config = SettingsConfigDict(
        env_prefix="INFRAMELD_JOBS__",
        extra="ignore",
        hide_input_in_errors=True,
        allow_inf_nan=False,
    )

    @model_validator(mode="after")
    def require_renewable_lease(self) -> Self:
        if self.lease_seconds <= 2 * self.database_timeout_seconds:
            raise ValueError("The job lease must exceed two database operation budgets.")
        return self
