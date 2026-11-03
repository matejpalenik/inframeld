from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.responses.own_organization_grant_response import (
    OwnOrganizationGrantResponse,
)


class MyOrganizationAccessResponse(BaseModel):
    organization_id: UUID = Field(serialization_alias="organizationId")
    principal_id: UUID = Field(serialization_alias="principalId")
    access_revision: int = Field(serialization_alias="accessRevision", ge=0, le=2**63 - 1)
    grants: tuple[OwnOrganizationGrantResponse, ...] = Field(max_length=4)
