from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class AccessGroupCreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    name: str = Field(
        strict=True, min_length=1, max_length=63, pattern="^[a-z](?:[a-z0-9-]*[a-z0-9])?$"
    )
    display_name: str = Field(alias="displayName", strict=True, min_length=1, max_length=128)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        ResourceName(value)
        return value

    @field_validator("display_name")
    @classmethod
    def _validate_label(cls, value: str) -> str:
        SubmittedDisplayName(value)
        return value
