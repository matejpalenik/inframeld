from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)


class OperationLookupAuthorityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: OperationLookupAuthorityFamily
    action_id: str = Field(alias="actionId", min_length=1, max_length=100)
