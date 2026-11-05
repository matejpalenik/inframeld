from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.enums.grant_target_kind import GrantTargetKind


class ProjectGrantTargetResponse(BaseModel):
    kind: Literal[GrantTargetKind.PROJECT]
    project_id: UUID = Field(serialization_alias="projectId")
