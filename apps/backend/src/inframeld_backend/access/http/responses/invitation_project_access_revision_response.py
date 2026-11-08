from uuid import UUID

from pydantic import BaseModel, Field


class InvitationProjectAccessRevisionResponse(BaseModel):
    project_id: UUID = Field(serialization_alias="projectId")
    access_revision: int = Field(serialization_alias="accessRevision")
