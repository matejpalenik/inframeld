from uuid import UUID

from pydantic import BaseModel, Field


class CurrentApplicationSessionResponse(BaseModel):
    principal_id: UUID = Field(serialization_alias="principalId")
    project_id: UUID = Field(serialization_alias="projectId")
