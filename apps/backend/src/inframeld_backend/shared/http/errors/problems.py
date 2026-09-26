"""Define the bounded RFC 9457 representation used by the HTTP adapter.

The HTTP layer constructs these models only from reviewed definitions and
sanitized issue data. Domain/application code must not import this module.
"""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyUrl, BaseModel, ConfigDict, Field, UrlConstraints

MAX_VALIDATION_ISSUES = 20
MAX_VALIDATION_PATH_SEGMENTS = 8

ProblemType = Annotated[AnyUrl, UrlConstraints(max_length=2048)]
FieldName = Annotated[str, Field(min_length=1, max_length=64)]
ArrayIndex = Annotated[int, Field(ge=0, strict=True)]
IssueLocation = Literal["body", "path", "query", "header", "cookie", "request"]
ErrorCode = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]


class ValidationIssue(BaseModel):
    """Describe one sanitized issue in an incoming request.

    Attributes:
        location: Request component containing the issue.
        path: Verified public field names or array indices, relative to that
            component. An empty path identifies the component as a whole.
        code: Product-owned validation category, independent of library names.
        message: Reviewed corrective description without submitted values.

    This model checks the output shape, not whether a string contains a secret.
    The validation translator must sanitize locations and messages first.
    """

    model_config = ConfigDict(extra="forbid")

    location: IssueLocation = Field(description="Request component containing the issue.")
    path: tuple[FieldName | ArrayIndex, ...] = Field(
        max_length=MAX_VALIDATION_PATH_SEGMENTS,
        description="Verified public fields and indices relative to the request component.",
    )
    code: ErrorCode = Field(description="Stable Inframeld validation category.")
    message: str = Field(
        min_length=1,
        max_length=256,
        description="Safe corrective description without submitted values.",
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
