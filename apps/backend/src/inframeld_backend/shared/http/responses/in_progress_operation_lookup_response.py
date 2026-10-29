from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InProgressOperationLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["in_progress"]
    operation_id: str = Field(alias="operationId")
