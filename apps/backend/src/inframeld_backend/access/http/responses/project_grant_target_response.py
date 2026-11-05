from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.project_departure_target_kind import (
    ProjectDepartureTargetKind,
)


class ProjectGrantTargetResponse(BaseModel):
    kind: Literal[ProjectDepartureTargetKind.PROJECT]
    project_id: UUID = Field(serialization_alias="projectId")
