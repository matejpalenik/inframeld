from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from inframeld_backend.access.application.value_objects.provider_credential_value import (
    ProviderCredentialValue,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ModelConnectionCredentialRequest(BaseModel):
    """Submit one provider key over the protected credential-management route."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    expected_credential_revision: int = Field(
        alias="expectedCredentialRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    value: SecretStr = Field(min_length=1, max_length=ProviderCredentialValue.MAX_BYTES, repr=False)

    @field_validator("value")
    @classmethod
    def _require_supported_token(cls, value: SecretStr) -> SecretStr:
        ProviderCredentialValue(value.get_secret_value())
        return value
