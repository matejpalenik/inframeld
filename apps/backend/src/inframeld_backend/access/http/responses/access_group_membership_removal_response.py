from typing import Literal
from uuid import UUID

from pydantic import Field

from inframeld_backend.access.http.responses.access_group_mutation_response import (
    AccessGroupMutationResponse,
)


class AccessGroupMembershipRemovalResponse(AccessGroupMutationResponse):
    principal_id: UUID = Field(serialization_alias="principalId")
    removed: Literal[True]
    changed: bool
