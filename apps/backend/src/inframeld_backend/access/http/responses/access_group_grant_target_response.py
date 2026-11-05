from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AccessGroupGrantTargetResponse(BaseModel):
    kind: Literal["access-group"]
    project_id: UUID = Field(serialization_alias="projectId")
    access_group_id: UUID = Field(serialization_alias="accessGroupId")
