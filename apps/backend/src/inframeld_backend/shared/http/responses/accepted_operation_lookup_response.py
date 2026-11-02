from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.http.enums.unknown_job_reference import UnknownJobReference
from inframeld_backend.shared.http.responses.known_job_reference_response import (
    KnownJobReferenceResponse,
)


class AcceptedOperationLookupResponse(BaseModel):
    """Confirm retained admission while making unknown dispatch and references explicit."""

    model_config = ConfigDict(extra="forbid")
    outcome: Literal["accepted_asynchronous"]
    operation_id: str = Field(alias="operationId")
    admission: Literal["confirmed"]
    job_reference: UnknownJobReference | KnownJobReferenceResponse = Field(alias="jobReference")
    dispatch: Literal["not_established"]
    idempotency_expires_at: datetime | None = Field(alias="idempotencyExpiresAt")
