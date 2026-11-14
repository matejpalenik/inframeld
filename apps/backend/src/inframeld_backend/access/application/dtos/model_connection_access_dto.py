from dataclasses import dataclass

from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider


@dataclass(frozen=True, slots=True)
class ModelConnectionAccessDTO:
    """Describe one complete non-secret provider configuration."""

    provider: ModelConnectionProvider
    base_url: str
    api_version: str | None
    authentication: ModelConnectionAuthentication
