from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectUploadDefaultRequest(BaseModel):
    """Replace the complete future-upload audience at an explicitly reviewed revision."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    group_ids: list[UUID] = Field(
        alias="groupIds",
        min_length=1,
        description="Complete nonempty same-Project audience. Every current and proposed group requires current management.",
    )
    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        description="Current Project Access revision reviewed for this complete replacement. A fresh no-op still requires this revision.",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )

    @field_validator("group_ids")
    @classmethod
    def _require_distinct_groups(cls, groups: list[UUID]) -> list[UUID]:
        if len(set(groups)) != len(groups):
            raise ValueError("The upload audience cannot repeat a group.")
        return groups
