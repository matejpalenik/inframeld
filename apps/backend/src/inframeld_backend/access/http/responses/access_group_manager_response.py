from typing import Literal
from uuid import UUID

from pydantic import Field

from inframeld_backend.access.http.responses.access_group_mutation_response import (
    AccessGroupMutationResponse,
)


class AccessGroupManagerResponse(AccessGroupMutationResponse):
    principal_id: UUID = Field(serialization_alias="principalId")
    manager: Literal[True]
    changed: bool
