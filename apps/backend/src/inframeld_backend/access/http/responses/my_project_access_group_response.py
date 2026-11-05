from uuid import UUID

from pydantic import BaseModel, Field


class MyProjectAccessGroupResponse(BaseModel):
    access_group_id: UUID = Field(serialization_alias="accessGroupId")
