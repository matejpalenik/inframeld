from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.indexing.http.requests.embedding_profile_definition_request import (
    EmbeddingProfileDefinitionRequest,
)
from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class EmbeddingProfileCreationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True, strict=True)

    name: str = Field(min_length=1, max_length=63, pattern="^[a-z](?:[a-z0-9-]*[a-z0-9])?$")
    display_name: str = Field(alias="displayName", min_length=1, max_length=128)
    definition: EmbeddingProfileDefinitionRequest

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return ResourceName(value).value

    @field_validator("display_name")
    @classmethod
    def _display_name(cls, value: str) -> str:
        return SubmittedDisplayName(value).value
