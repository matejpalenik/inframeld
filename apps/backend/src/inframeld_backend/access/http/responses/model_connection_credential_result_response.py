from datetime import datetime

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.model_connection_credential_details_response import (
    ModelConnectionCredentialDetailsResponse,
)


class ModelConnectionCredentialResultResponse(BaseModel):
    """Original safe receipt and whether this response recovered a completed request."""

    credential: ModelConnectionCredentialDetailsResponse
    changed: bool
    replayed: bool
    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
