from typing import Literal

from inframeld_backend.access.http.responses.access_group_mutation_response import (
    AccessGroupMutationResponse,
)


class AccessGroupDeletionResponse(AccessGroupMutationResponse):
    removed: Literal[True]
