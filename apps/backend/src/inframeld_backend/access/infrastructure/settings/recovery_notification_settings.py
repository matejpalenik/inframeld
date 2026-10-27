from datetime import datetime
from pathlib import Path
from typing import Annotated, Self

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import NoDecode

from inframeld_backend.access.application.enums.identity_recovery_event_kind import (
    IdentityRecoveryEventKind,
)
from inframeld_backend.access.domain.value_objects.identity_authority import IdentityAuthority


class RecoveryNotificationSettings(BaseModel):
    authority: Annotated[IdentityAuthority, NoDecode]
    event_kind: IdentityRecoveryEventKind = IdentityRecoveryEventKind.RECOVERY
    current_key_file: Path
    retiring_key_file: Path | None = None
    retiring_key_accept_until: datetime | None = None
    request_timeout_seconds: float = Field(default=10.0, gt=0, le=60, allow_inf_nan=False)
    database_timeout_seconds: float = Field(default=5.0, gt=0, le=5, allow_inf_nan=False)

    @field_validator("authority", mode="before")
    @classmethod
    def _authority(cls, value: object) -> IdentityAuthority:
        if isinstance(value, IdentityAuthority):
            return value
        if isinstance(value, str):
            return IdentityAuthority(value)
        raise ValueError("A configured provider authority is required.")

    @model_validator(mode="after")
    def _rotation(self) -> Self:
        if (self.retiring_key_file is None) != (self.retiring_key_accept_until is None):
            raise ValueError("A retiring key requires an explicit acceptance deadline.")
        if (
            self.retiring_key_accept_until is not None
            and self.retiring_key_accept_until.utcoffset() is None
        ):
            raise ValueError("The retiring-key deadline must include a timezone.")
        if self.database_timeout_seconds >= self.request_timeout_seconds:
            raise ValueError("The request budget must exceed the database budget.")
        return self
