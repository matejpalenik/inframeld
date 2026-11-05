from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.own_organization_grant_response import (
    OwnOrganizationGrantResponse,
)
from inframeld_backend.shared.domain.validation.revision_validation import RevisionValidation


class MyOrganizationAccessResponse(BaseModel):
    organization_id: UUID = Field(serialization_alias="organizationId")
    principal_id: UUID = Field(serialization_alias="principalId")
    access_revision: int = Field(
        serialization_alias="accessRevision",
        ge=0,
        le=RevisionValidation.MAX_VALUE,
        strict=True,
        json_schema_extra={"format": "int64"},
    )
    grants: tuple[OwnOrganizationGrantResponse, ...] = Field(max_length=4)
