from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.application.enums.operation_lookup_outcome import (
    OperationLookupOutcome,
)
from inframeld_backend.shared.http.enums.operation_admission_confirmation import (
    OperationAdmissionConfirmation,
)
from inframeld_backend.shared.http.enums.operation_dispatch_establishment import (
    OperationDispatchEstablishment,
)
from inframeld_backend.shared.http.enums.unknown_job_reference import UnknownJobReference
from inframeld_backend.shared.http.responses.known_job_reference_response import (
    KnownJobReferenceResponse,
)


class AcceptedOperationLookupResponse(BaseModel):
    """Confirm retained admission while making unknown dispatch and references explicit."""

    model_config = ConfigDict(extra="forbid")
    outcome: Literal[OperationLookupOutcome.ACCEPTED_ASYNCHRONOUS]
    operation_id: str = Field(alias="operationId")
    admission: Literal[OperationAdmissionConfirmation.CONFIRMED]
    job_reference: UnknownJobReference | KnownJobReferenceResponse = Field(alias="jobReference")
    dispatch: Literal[OperationDispatchEstablishment.NOT_ESTABLISHED]
    idempotency_expires_at: datetime | None = Field(alias="idempotencyExpiresAt")
