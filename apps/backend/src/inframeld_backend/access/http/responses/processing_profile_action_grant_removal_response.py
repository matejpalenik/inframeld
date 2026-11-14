from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.indexing.domain.enums.processing_profile_action import (
    ProcessingProfileAction,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ProcessingProfileActionGrantRemovalResponse(BaseModel):
    operation_id: str = Field(serialization_alias="operationId", min_length=1, max_length=128)
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    processing_profile_id: UUID = Field(serialization_alias="processingProfileId")
    recipient_principal_id: UUID = Field(serialization_alias="recipientPrincipalId")
    action_id: ProcessingProfileAction = Field(serialization_alias="actionId")
    removed: Literal[True]
    access_revision: int = Field(
        serialization_alias="accessRevision",
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        strict=True,
        json_schema_extra={"format": "int64"},
    )
    changed: bool
