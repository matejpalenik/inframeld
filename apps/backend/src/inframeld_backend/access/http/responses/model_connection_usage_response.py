from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.shared.application.enums.model_role import ModelRole
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class _UsageObservationResponse(BaseModel):
    source: Literal["preflight", "real-use"]
    connection_access_revision: int = Field(
        serialization_alias="connectionAccessRevision",
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    credential_revision: int = Field(
        serialization_alias="credentialRevision",
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    observed_at: datetime = Field(serialization_alias="observedAt")


class _UsageAttemptResponse(_UsageObservationResponse):
    outcome: Literal["accepted", "failed", "uncertain"]


class _UsageValidationResponse(_UsageObservationResponse):
    status: Literal["validated", "stale"]


class ModelConnectionUsageResponse(BaseModel):
    """Describe a visible consumer's actual attempt and independently available validation."""

    consumer_kind: Literal[
        "pipeline-version", "embedding-profile", "processing-profile", "evaluation-suite"
    ] = Field(serialization_alias="consumerKind")
    consumer_id: UUID = Field(serialization_alias="consumerId")
    role: ModelRole
    model: str
    latest_attempt: _UsageAttemptResponse | None = Field(serialization_alias="latestAttempt")
    last_validation: _UsageValidationResponse | None = Field(serialization_alias="lastValidation")
