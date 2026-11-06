from typing import Literal
from uuid import UUID

from pydantic import Field

from inframeld_backend.access.http.responses.access_group_mutation_response import (
    AccessGroupMutationResponse,
)


class AccessGroupMembershipResponse(AccessGroupMutationResponse):
    principal_id: UUID = Field(serialization_alias="principalId")
    member: Literal[True]
    changed: bool
