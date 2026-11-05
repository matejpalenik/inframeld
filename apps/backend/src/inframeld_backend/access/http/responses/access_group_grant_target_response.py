from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.enums.grant_target_kind import GrantTargetKind


class AccessGroupGrantTargetResponse(BaseModel):
    kind: Literal[GrantTargetKind.ACCESS_GROUP]
    project_id: UUID = Field(serialization_alias="projectId")
    access_group_id: UUID = Field(serialization_alias="accessGroupId")
