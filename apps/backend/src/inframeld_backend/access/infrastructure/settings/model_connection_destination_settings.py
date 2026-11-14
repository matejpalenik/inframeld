from typing import Self

from pydantic import BaseModel, ConfigDict, model_validator

from inframeld_backend.access.domain.policies.model_connection_destination_policy import (
    ModelConnectionDestinationPolicy,
)


class ModelConnectionDestinationSettings(BaseModel):
    """Deployment-owned exact base URLs with a separate local Ollama exception."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    https_base_urls: frozenset[str] = frozenset()
    local_ollama_base_urls: frozenset[str] = frozenset()

    @model_validator(mode="after")
    def require_supported_destinations(self) -> Self:
        if any(
            not ModelConnectionDestinationPolicy.is_supported_base_url(url, scheme="https")
            for url in self.https_base_urls
        ) or any(
            not ModelConnectionDestinationPolicy.is_supported_base_url(
                url, scheme="http", loopback=True
            )
            for url in self.local_ollama_base_urls
        ):
            raise ValueError("A configured model destination is unsupported.")
        return self
