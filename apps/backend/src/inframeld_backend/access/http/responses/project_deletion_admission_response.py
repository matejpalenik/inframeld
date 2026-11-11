from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProjectDeletionAdmissionResponse(BaseModel):
    """Expose original admission, never internal execution or physical progress."""

    model_config = ConfigDict(extra="forbid")
    operation_id: str = Field(serialization_alias="operationId", min_length=1, max_length=128)
    idempotency_expires_at: AwareDatetime | None = Field(serialization_alias="idempotencyExpiresAt")
    project_id: UUID = Field(serialization_alias="projectId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    admission_confirmed: Literal[True] = Field(serialization_alias="admissionConfirmed")
    access_blocked: Literal[True] = Field(serialization_alias="accessBlocked")
