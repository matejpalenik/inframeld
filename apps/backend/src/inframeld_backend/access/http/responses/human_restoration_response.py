from datetime import UTC, datetime
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class HumanRestorationResponse(BaseModel):
    """Return the original safe receipt without inferring current account state."""

    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(serialization_alias="operationId", min_length=1, max_length=128)
    idempotency_expires_at: AwareDatetime = Field(serialization_alias="idempotencyExpiresAt")
    organization_id: UUID = Field(serialization_alias="organizationId")
    principal_id: UUID = Field(serialization_alias="principalId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )

    @field_validator("idempotency_expires_at")
    @classmethod
    def normalize_expiry(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
