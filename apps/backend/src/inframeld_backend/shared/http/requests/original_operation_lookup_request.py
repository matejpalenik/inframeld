from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.http.requests.operation_lookup_authority_request import (
    OperationLookupAuthorityRequest,
)


class OriginalOperationLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    installation_id: UUID = Field(alias="installationId")
    organization_id: UUID = Field(alias="organizationId")
    project_id: UUID | None = Field(alias="projectId")
    method: Literal["POST", "PUT", "PATCH", "DELETE"]
    requested_route: str = Field(alias="requestedRoute", min_length=1)
    key: str = Field(min_length=1, max_length=128)
    expected_authority: OperationLookupAuthorityRequest = Field(alias="expectedAuthority")
