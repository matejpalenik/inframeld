from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.model_connection_action import ModelConnectionAction
from inframeld_backend.access.http.responses.model_connection_grant_target_response import (
    ModelConnectionGrantTargetResponse,
)
from inframeld_backend.access.http.responses.model_connection_response import (
    ModelConnectionResponse,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class InitialModelConnectionGrantResponse(BaseModel):
    target: ModelConnectionGrantTargetResponse
    action_id: ModelConnectionAction = Field(serialization_alias="actionId")
    can_grant: Literal[True] = Field(serialization_alias="canGrant")


class ModelConnectionCreationResponse(BaseModel):
    connection: ModelConnectionResponse
    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    project_access_revision: int = Field(
        serialization_alias="projectAccessRevision",
        ge=1,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
    initial_grants: tuple[InitialModelConnectionGrantResponse, ...] = Field(
        serialization_alias="initialGrants",
        min_length=4,
        max_length=4,
    )
