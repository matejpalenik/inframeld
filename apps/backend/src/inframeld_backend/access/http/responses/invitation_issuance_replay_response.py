from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.access.http.types.invitation_assignment_request import (
    InvitationAssignmentRequest,
)


class InvitationIssuanceReplayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    operation_id: str = Field(serialization_alias="operationId")
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
    invitation_id: UUID = Field(serialization_alias="invitationId")
    organization_id: UUID = Field(serialization_alias="organizationId")
    assignments: list[InvitationAssignmentRequest]
    expires_at: datetime = Field(serialization_alias="expiresAt")
    access_revision: int = Field(serialization_alias="accessRevision")
    secret_available: Literal[False] = Field(alias="secretAvailable")
