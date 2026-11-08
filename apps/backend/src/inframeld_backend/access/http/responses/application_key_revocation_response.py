from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.access.http.responses.application_key_metadata_response import (
    ApplicationKeyMetadataResponse,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationKeyRevocationResponse(BaseModel):
    """Return the original safe receipt for a revocation or an already-revoked no-op."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    operation_id: str = Field(serialization_alias="operationId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    metadata: ApplicationKeyMetadataResponse
