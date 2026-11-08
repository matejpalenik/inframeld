from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class InvitationProjectAccessRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    project_id: UUID = Field(alias="projectId")
    access_revision: int = Field(
        alias="accessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
