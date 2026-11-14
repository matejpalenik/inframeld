from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider


class ModelConnectionAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    provider: ModelConnectionProvider
    base_url: str = Field(alias="baseUrl", strict=True, min_length=1, max_length=2048)
    api_version: str | None = Field(alias="apiVersion", strict=True, max_length=128)
    authentication: ModelConnectionAuthentication
