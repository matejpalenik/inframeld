from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.initial_project_grant_response import (
    InitialProjectGrantResponse,
)


class ProjectCreationResponse(BaseModel):
    """Report original creation assignments, not a present permission snapshot."""

    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    organization_id: UUID = Field(serialization_alias="organizationId")
    project_id: UUID = Field(serialization_alias="projectId")
    name: str
    display_name: str = Field(serialization_alias="displayName")
    access_revision: Literal[1] = Field(serialization_alias="accessRevision")
    metadata_revision: Literal[0] = Field(serialization_alias="metadataRevision")
    initial_grants: tuple[InitialProjectGrantResponse, ...] = Field(
        serialization_alias="initialGrants", min_length=18, max_length=18
    )
