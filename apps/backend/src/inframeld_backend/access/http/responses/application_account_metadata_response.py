from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.principal_status import PrincipalStatus
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationAccountMetadataResponse(BaseModel):
    project_id: UUID = Field(serialization_alias="projectId")
    principal_id: UUID = Field(serialization_alias="principalId")
    name: str | None
    display_name: str = Field(serialization_alias="displayName")
    status: PrincipalStatus
    created_at: datetime = Field(serialization_alias="createdAt")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
