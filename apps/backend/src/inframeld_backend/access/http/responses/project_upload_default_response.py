from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectUploadDefaultResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    project_id: UUID = Field(
        serialization_alias="projectId",
        description="Exact Project whose saved future-upload audience is represented.",
    )
    access_revision: int = Field(
        serialization_alias="accessRevision",
        description="Project Access revision of this current read or immutable original result.",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    group_ids: list[UUID] | None = Field(
        serialization_alias="groupIds",
        min_length=1,
        description="UUID-sorted saved audience, or null only when this valid Project has no saved default.",
    )
