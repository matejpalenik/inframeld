"""Describe the accepted project grant operation safely."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectUseOnlyGrantResponse(BaseModel):
    """Describe the original change - current grants require a fresh authorized read."""

    operation_id: str = Field(serialization_alias="operationId")
    project_id: UUID = Field(serialization_alias="projectId")
    recipient_principal_id: UUID = Field(serialization_alias="recipientPrincipalId")
    action_id: Literal["create-access-groups"] = Field(serialization_alias="actionId")
    can_grant: Literal[False] = Field(default=False, serialization_alias="canGrant")
    access_revision: int = Field(serialization_alias="accessRevision")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
