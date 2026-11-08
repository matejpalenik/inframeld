from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class InvitationRevocationResponse(BaseModel):
    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    invitation_id: UUID = Field(serialization_alias="invitationId")
    organization_id: UUID = Field(serialization_alias="organizationId")
    access_revision: int = Field(serialization_alias="accessRevision")
    revoked: Literal[True] = True
