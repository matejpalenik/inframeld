from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.access.application.value_objects.suspension_reason import SuspensionReason
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class HumanSuspensionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    reason: str = Field(
        alias="reason",
        strict=True,
        min_length=1,
        max_length=SuspensionReason.MAX_LENGTH,
        description="Required safe single-line audit text, at most 512 Unicode characters.",
    )

    @field_validator("reason")
    @classmethod
    def validate_audit_text(cls, value: str) -> str:
        return SuspensionReason(value).value
