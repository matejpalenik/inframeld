from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.access.http.requests.model_connection_access_request import (
    ModelConnectionAccessRequest,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class ModelConnectionCreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    name: str = Field(
        strict=True, min_length=1, max_length=63, pattern="^[a-z](?:[a-z0-9-]*[a-z0-9])?$"
    )
    display_name: str = Field(alias="displayName", strict=True, min_length=1, max_length=128)
    access: ModelConnectionAccessRequest

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return ResourceName(value).value

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str) -> str:
        return SubmittedDisplayName(value).value
