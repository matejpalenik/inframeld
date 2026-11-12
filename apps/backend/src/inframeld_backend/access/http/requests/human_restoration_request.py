from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.access.application.value_objects.security_review_reference import (
    SecurityReviewReference,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class HumanRestorationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    security_review_reference: str = Field(
        alias="securityReviewReference",
        strict=True,
        min_length=1,
        max_length=SecurityReviewReference.MAX_LENGTH,
        description="Required safe single-line audit text, at most 128 Unicode characters.",
    )

    @field_validator("security_review_reference")
    @classmethod
    def validate_audit_text(cls, value: str) -> str:
        return SecurityReviewReference(value).value
