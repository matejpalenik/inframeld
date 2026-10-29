from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CompletedOperationLookupResponse(BaseModel):
    """Expose safe synchronous outcome metadata without replaying content."""

    model_config = ConfigDict(extra="forbid")
    outcome: Literal["completed_synchronous"]
    operation_id: str = Field(alias="operationId")
    classification: Literal["safe_result", "issued_secret", "answer_receipt"]
    idempotency_expires_at: datetime = Field(alias="idempotencyExpiresAt")
