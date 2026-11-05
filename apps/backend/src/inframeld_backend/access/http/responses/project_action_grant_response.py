from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectActionGrantResponse(BaseModel):
    operation_id: str = Field(serialization_alias="operationId", min_length=1, max_length=128)
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    project_id: UUID = Field(serialization_alias="projectId")
    recipient_principal_id: UUID = Field(serialization_alias="recipientPrincipalId")
    action_id: str = Field(serialization_alias="actionId")
    can_grant: bool = Field(serialization_alias="canGrant")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        strict=True,
        json_schema_extra={"format": "int64"},
    )
    changed: bool
