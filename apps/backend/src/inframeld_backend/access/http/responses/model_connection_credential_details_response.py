from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ModelConnectionCredentialDetailsResponse(BaseModel):
    """Safe details of the exact credential slot at the observed revision."""

    project_id: UUID = Field(serialization_alias="projectId")
    model_connection_id: UUID = Field(serialization_alias="modelConnectionId")
    credential_id: UUID | None = Field(serialization_alias="credentialId")
    revision: int = Field(
        ge=0, le=RevisionValidation.MAX_VALUE, json_schema_extra={"format": "int64"}
    )
    present: bool
    changed_at: datetime | None = Field(serialization_alias="changedAt")
