from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectMembershipRemovalResponse(BaseModel):
    """Report original removal, independently of a later rejoin."""

    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    project_id: UUID = Field(serialization_alias="projectId")
    principal_id: UUID = Field(serialization_alias="principalId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    removed: Literal[True]
    changed: bool
