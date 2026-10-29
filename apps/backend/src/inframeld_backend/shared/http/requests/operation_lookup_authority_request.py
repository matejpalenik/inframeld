from pydantic import BaseModel, ConfigDict, Field, field_validator

from inframeld_backend.shared.application.enums.operation_lookup_authority_family import (
    OperationLookupAuthorityFamily,
)


class OperationLookupAuthorityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family: OperationLookupAuthorityFamily
    action_id: str = Field(alias="actionId", min_length=1, max_length=100)

    @field_validator("action_id")
    @classmethod
    def require_nonblank(cls, value: str) -> str:
        """Reject blank identity fields without changing their original bytes."""
        if not value.strip():
            raise ValueError("An original identity field must be nonblank.")
        return value
