from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectMembershipResponse(BaseModel):
    """Report original bare membership, without restoring grants or later state."""

    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    project_id: UUID = Field(serialization_alias="projectId")
    principal_id: UUID = Field(serialization_alias="principalId")
    access_revision: int = Field(serialization_alias="accessRevision")
    member: Literal[True]
    changed: bool
