from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.http.types.problem_field_types import (
    MAX_VALIDATION_PATH_SEGMENTS,
    ArrayIndex,
    ErrorCode,
    FieldName,
    IssueLocation,
)


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
