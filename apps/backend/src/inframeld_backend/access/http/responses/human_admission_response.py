from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class HumanAdmissionResponse(BaseModel):
    """Describe original admission, without promising starter or setup readiness."""

    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    organization_id: UUID = Field(serialization_alias="organizationId")
    principal_id: UUID = Field(serialization_alias="principalId")
    access_revision: int = Field(serialization_alias="accessRevision")
    changed: bool
