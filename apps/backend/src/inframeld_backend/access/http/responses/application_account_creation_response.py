from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.initial_application_account_grant_response import (
    InitialApplicationAccountGrantResponse,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationAccountCreationResponse(BaseModel):
    """Report original human creator assignments, not current account permissions."""

    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    project_id: UUID = Field(serialization_alias="projectId")
    principal_id: UUID = Field(serialization_alias="principalId")
    name: str
    display_name: str = Field(serialization_alias="displayName")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        strict=True,
        ge=1,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    initial_grants: tuple[InitialApplicationAccountGrantResponse, ...] = Field(
        serialization_alias="initialGrants", min_length=3, max_length=3
    )
