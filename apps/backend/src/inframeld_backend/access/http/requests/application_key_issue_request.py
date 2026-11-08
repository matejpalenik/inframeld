from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.json_schema import SkipJsonSchema

from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.policies.application_key_lifetime_policy import (
    ApplicationKeyLifetimePolicy,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ApplicationKeyIssueRequest(BaseModel):
    """Preserve adapter order and omitted lifetime without caller audiences."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    allowed_adapters: list[ApplicationKeyAdapter] = Field(
        alias="allowedAdapters", min_length=1, max_length=2, json_schema_extra={"uniqueItems": True}
    )
    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    expires_in_seconds: (
        Annotated[
            int,
            Field(
                strict=True,
                gt=0,
                le=ApplicationKeyLifetimePolicy.MAXIMUM_SECONDS,
                json_schema_extra={"format": "int64"},
            ),
        ]
        | SkipJsonSchema[None]
    ) = Field(default=None, alias="expiresInSeconds")

    @model_validator(mode="after")
    def _require_exact_selection(self) -> Self:
        if len(set(self.allowed_adapters)) != len(self.allowed_adapters):
            raise ValueError("Select each application-key adapter exactly once.")
        if "expires_in_seconds" in self.model_fields_set and self.expires_in_seconds is None:
            raise ValueError("A submitted application-key lifetime cannot be null.")
        return self
