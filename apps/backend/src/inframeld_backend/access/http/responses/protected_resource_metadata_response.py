from typing import Literal

from pydantic import BaseModel, ConfigDict

from inframeld_backend.access.domain.enums.human_oauth_scope import HumanOAuthScope
from inframeld_backend.access.http.enums.credential_transport_location import (
    CredentialTransportLocation,
)
from inframeld_backend.access.http.responses.inframeld_discovery_response import (
    InframeldDiscoveryResponse,
)


class ProtectedResourceMetadataResponse(BaseModel):
    """Publish the bounded first-party RFC 9728 profile, not private provider configuration."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    resource: str
    authorization_servers: tuple[str]
    scopes_supported: tuple[Literal[HumanOAuthScope.API]]
    bearer_methods_supported: tuple[Literal[CredentialTransportLocation.HEADER]]
    inframeld: InframeldDiscoveryResponse
