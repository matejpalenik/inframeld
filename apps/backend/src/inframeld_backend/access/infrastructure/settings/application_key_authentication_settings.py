from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from inframeld_backend.access.application.dtos.application_key_verification_profile_dto import (
    ApplicationKeyVerificationProfileDTO,
)
from inframeld_backend.access.domain.enums.application_key_adapter import ApplicationKeyAdapter
from inframeld_backend.access.domain.value_objects.application_key_audience import (
    ApplicationKeyAudience,
)
from inframeld_backend.access.infrastructure.types.application_key_transport_profile import (
    ApplicationKeyTransportProfile,
)
from inframeld_backend.access.infrastructure.verifiers.pydantic_discovery_url_verifier import (
    PydanticDiscoveryURLVerifier,
)


class ApplicationKeyAuthenticationSettings(BaseModel):
    """Supply trusted adapter profiles for exact verification and fresh issuance bindings."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    http_audience: str | None = None
    mcp_audience: str | None = None
    transport_profile: ApplicationKeyTransportProfile = ApplicationKeyTransportProfile.HTTPS
    total_timeout_seconds: float = Field(default=10.0, gt=0, allow_inf_nan=False)

    @field_validator("total_timeout_seconds", mode="before")
    @classmethod
    def _reject_boolean_timeout(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Authentication timeout must be finite and positive.")
        return value

    @model_validator(mode="after")
    def _validate_profiles(self) -> Self:
        for audience in (self.http_audience, self.mcp_audience):
            if audience is not None:
                PydanticDiscoveryURLVerifier.require_public(
                    audience,
                    managed_local=self.transport_profile
                    is ApplicationKeyTransportProfile.MANAGED_LOCAL,
                )
        return self

    def profile(
        self, adapter: ApplicationKeyAdapter
    ) -> ApplicationKeyVerificationProfileDTO | None:
        audience = (
            self.http_audience if adapter is ApplicationKeyAdapter.HTTP else self.mcp_audience
        )
        return (
            ApplicationKeyVerificationProfileDTO(ApplicationKeyAudience(audience), adapter)
            if audience is not None
            else None
        )
