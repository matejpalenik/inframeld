from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.invitation_project_access_revision_response import (
    InvitationProjectAccessRevisionResponse,
)


class InvitationActivationResponse(BaseModel):
    operation_id: str = Field(serialization_alias="operationId")
    invitation_id: UUID = Field(serialization_alias="invitationId")
    organization_id: UUID = Field(serialization_alias="organizationId")
    principal_id: UUID = Field(serialization_alias="principalId")
    organization_access_revision: int = Field(serialization_alias="organizationAccessRevision")
    project_access_revisions: list[InvitationProjectAccessRevisionResponse] = Field(
        serialization_alias="projectAccessRevisions"
    )
    idempotency_expires_at: datetime = Field(serialization_alias="idempotencyExpiresAt")
