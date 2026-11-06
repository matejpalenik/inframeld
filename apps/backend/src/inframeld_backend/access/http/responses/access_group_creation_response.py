from uuid import UUID

from pydantic import Field

from inframeld_backend.access.http.responses.access_group_mutation_response import (
    AccessGroupMutationResponse,
)


class AccessGroupCreationResponse(AccessGroupMutationResponse):
    name: str
    display_name: str = Field(serialization_alias="displayName")
    creator_principal_id: UUID = Field(serialization_alias="creatorPrincipalId")
