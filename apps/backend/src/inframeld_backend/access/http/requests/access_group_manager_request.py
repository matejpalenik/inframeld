from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class AccessGroupManagerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
