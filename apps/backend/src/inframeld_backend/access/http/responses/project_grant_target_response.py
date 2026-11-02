from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectGrantTargetResponse(BaseModel):
    kind: Literal["project"]
    project_id: UUID = Field(serialization_alias="projectId")
