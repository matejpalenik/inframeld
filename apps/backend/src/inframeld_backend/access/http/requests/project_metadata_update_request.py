from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.json_schema import SkipJsonSchema

from inframeld_backend.shared.domain.value_objects.resource_name import ResourceName
from inframeld_backend.shared.domain.value_objects.submitted_display_name import (
    SubmittedDisplayName,
)


class ProjectMetadataUpdateRequest(BaseModel):
    """Omitted fields preserve stored values. Explicit null never clears either field."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_metadata_revision: int = Field(
        alias="expectedMetadataRevision",
        strict=True,
        ge=0,
        le=2**63 - 1,
        description="Metadata revision reviewed for this exact change.",
    )
    name: (
        Annotated[str, Field(min_length=1, max_length=63, pattern="^[a-z](?:[a-z0-9-]*[a-z0-9])?$")]
        | SkipJsonSchema[None]
    ) = Field(
        default=None,
        description="Explicit exact selector replacement. Omit to preserve the current selector.",
    )
    display_name: Annotated[str, Field(min_length=1, max_length=128)] | SkipJsonSchema[None] = (
        Field(
            default=None,
            alias="displayName",
            description="New label in Unicode code points. Omit to preserve even an unrestricted legacy label.",
        )
    )

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            ResourceName(value)
        return value

    @field_validator("display_name")
    @classmethod
    def _validate_label(cls, value: str | None) -> str | None:
        if value is not None:
            SubmittedDisplayName(value)
        return value

    @model_validator(mode="after")
    def _require_replacement(self) -> Self:
        if ("name" in self.model_fields_set and self.name is None) or (
            "display_name" in self.model_fields_set and self.display_name is None
        ):
            raise ValueError("A submitted replacement cannot be null.")
        if self.name is None and self.display_name is None:
            raise ValueError("Submit at least one replacement field.")
        return self
