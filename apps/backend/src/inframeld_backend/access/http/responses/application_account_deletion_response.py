from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationAccountDeletionResponse(BaseModel):
    """Describe committed local retirement, preserving the original safe receipt."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    operation_id: str = Field(serialization_alias="operationId", min_length=1, max_length=128)
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    project_id: UUID = Field(serialization_alias="projectId")
    principal_id: UUID = Field(serialization_alias="principalId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        strict=True,
        ge=1,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    access_blocked: Literal[True] = Field(serialization_alias="accessBlocked")
