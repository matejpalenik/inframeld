from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.my_project_access_grant_response import (
    MyProjectAccessGrantResponse,
)
from inframeld_backend.access.http.responses.my_project_access_group_response import (
    MyProjectAccessGroupResponse,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class MyProjectAccessResponse(BaseModel):
    project_id: UUID = Field(serialization_alias="projectId")
    principal_id: UUID = Field(serialization_alias="principalId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        strict=True,
        json_schema_extra={"format": "int64"},
    )
    grants: list[MyProjectAccessGrantResponse]
    group_memberships: list[MyProjectAccessGroupResponse] = Field(
        serialization_alias="groupMemberships"
    )
    group_managements: list[MyProjectAccessGroupResponse] = Field(
        serialization_alias="groupManagements"
    )
    next_cursor: str | None = Field(serialization_alias="nextCursor")
