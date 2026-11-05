from uuid import UUID

from pydantic import Field

from inframeld_backend.access.http.responses.project_member_response import ProjectMemberResponse
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.http.responses.page_response import PageResponse


class ProjectMembersPageResponse(PageResponse[ProjectMemberResponse]):
    project_id: UUID = Field(serialization_alias="projectId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        ge=0,
        strict=True,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
