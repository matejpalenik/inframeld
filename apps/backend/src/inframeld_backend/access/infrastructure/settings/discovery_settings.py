from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from inframeld_backend.access.infrastructure.types.discovery_transport_profile import (
    DiscoveryTransportProfile,
)
from inframeld_backend.access.infrastructure.verifiers.pydantic_discovery_url_verifier import (
    PydanticDiscoveryURLVerifier,
)


class DiscoverySettings(BaseModel):
    """Configure public API identity separately from private provider endpoints."""

    model_config = ConfigDict(frozen=True, extra="forbid", hide_input_in_errors=True)
    public_api_url: str
    transport_profile: DiscoveryTransportProfile = DiscoveryTransportProfile.HTTPS

    @model_validator(mode="after")
    def _validate_identity(self) -> Self:
        PydanticDiscoveryURLVerifier.require_public(
            self.public_api_url,
            managed_local=self.transport_profile == DiscoveryTransportProfile.MANAGED_LOCAL,
        )
        return self
