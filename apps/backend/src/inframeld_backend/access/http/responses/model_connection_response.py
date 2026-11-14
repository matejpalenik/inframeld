from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.model_connection_authentication import (
    ModelConnectionAuthentication,
)
from inframeld_backend.access.domain.enums.model_connection_provider import ModelConnectionProvider
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class ModelConnectionAccessResponse(BaseModel):
    provider: ModelConnectionProvider
    base_url: str = Field(serialization_alias="baseUrl")
    api_version: str | None = Field(serialization_alias="apiVersion")
    authentication: ModelConnectionAuthentication


class ModelConnectionCredentialResponse(BaseModel):
    present: bool
    revision: int = Field(
        ge=0, le=RevisionValidation.MAX_VALUE, json_schema_extra={"format": "int64"}
    )


class ModelConnectionResponse(BaseModel):
    """Return only current configuration and public credential presence metadata."""

    project_id: UUID = Field(serialization_alias="projectId")
    model_connection_id: UUID = Field(serialization_alias="modelConnectionId")
    name: str
    display_name: str = Field(serialization_alias="displayName")
    access: ModelConnectionAccessResponse
    connection_access_revision: int = Field(
        serialization_alias="connectionAccessRevision",
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    credential: ModelConnectionCredentialResponse
