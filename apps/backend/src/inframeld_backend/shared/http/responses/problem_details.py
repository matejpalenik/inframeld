from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.http.responses.validation_issue import ValidationIssue
from inframeld_backend.shared.http.types.problem_field_types import (
    MAX_VALIDATION_ISSUES,
    ErrorCode,
    ProblemType,
)


class ProblemDetails(BaseModel):
    """Represent an Inframeld HTTP error using RFC 9457 Problem Details.

    Attributes:
        type: Absolute problem URI; about:blank is used for generic HTTP errors.
        title: Short public summary without occurrence-specific internal data.
        status: Error status in the range 400 through 599.
        detail: Safe public explanation selected by the HTTP adapter.
        code: Stable public code; clients must tolerate unfamiliar future codes.
        request_id: Correlation UUID serialized as requestId, never authorization.
        errors: Optional bounded collection of already sanitized request issues.

    The response builder enforces the selected definition's type/code/status
    pairing and whether errors is appropriate. This model does not map Python
    exceptions, authenticate callers, authorize retries, or render tracebacks.
    Server-side extra fields are rejected; client parsers must still tolerate
    future RFC extension members.
    """

    model_config = ConfigDict(
        extra="forbid",
        validate_by_name=True,
        serialize_by_alias=True,
    )

    type: ProblemType = Field(description="Primary RFC 9457 problem-type URI.")
    title: str = Field(
        min_length=1,
        max_length=128,
        description="Stable human-readable summary of the problem type.",
    )
    status: int = Field(
        ge=400,
        le=599,
        strict=True,
        description="HTTP error status, equal to the actual response status.",
    )
    detail: str = Field(
        min_length=1,
        max_length=512,
        description="Reviewed explanation without internal or submitted sensitive values.",
    )
    code: ErrorCode = Field(description="Stable Inframeld code paired with the problem type.")
    request_id: UUID = Field(
        alias="requestId",
        description="Server request identifier, also returned in X-Request-ID.",
    )
    errors: tuple[ValidationIssue, ...] | None = Field(
        default=None,
        max_length=MAX_VALIDATION_ISSUES,
        description="At most 20 sanitized issues; the list may be incomplete.",
    )
