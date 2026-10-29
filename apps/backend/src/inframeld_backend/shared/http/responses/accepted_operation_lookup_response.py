from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AcceptedOperationLookupResponse(BaseModel):
    """Confirm retained admission while making unknown dispatch and references explicit."""

    model_config = ConfigDict(extra="forbid")
    outcome: Literal["accepted_asynchronous"] = "accepted_asynchronous"
    operation_id: str = Field(alias="operationId")
    admission: Literal["confirmed"] = "confirmed"
    job_reference: Literal["unknown"] = Field(default="unknown", alias="jobReference")
    job_id: None = Field(alias="jobId")
    dispatch: Literal["not_established"] = "not_established"
    idempotency_expires_at: datetime | None = Field(alias="idempotencyExpiresAt")
