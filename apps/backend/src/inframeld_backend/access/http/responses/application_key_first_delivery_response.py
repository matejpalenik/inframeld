from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.access.http.responses.application_key_metadata_response import (
    ApplicationKeyMetadataResponse,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationKeyFirstDeliveryResponse(BaseModel):
    """Deliver the new credential only after its original issuance commits."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    operation_id: str = Field(serialization_alias="operationId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        strict=True,
        ge=1,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    metadata: ApplicationKeyMetadataResponse
    secret_available: Literal[True] = Field(alias="secretAvailable")
    key: str = Field(repr=False)
