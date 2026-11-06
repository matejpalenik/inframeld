from uuid import UUID

from pydantic import Field

from inframeld_backend.access.http.responses.access_group_principal_response import (
    AccessGroupPrincipalResponse,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation
from inframeld_backend.shared.http.responses.page_response import PageResponse


class AccessGroupPrincipalsPageResponse(PageResponse[AccessGroupPrincipalResponse]):
    project_id: UUID = Field(serialization_alias="projectId")
    access_group_id: UUID = Field(serialization_alias="accessGroupId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        ge=0,
        strict=True,
        le=RevisionValidation.MAX_VALUE,
        json_schema_extra={"format": "int64"},
    )
