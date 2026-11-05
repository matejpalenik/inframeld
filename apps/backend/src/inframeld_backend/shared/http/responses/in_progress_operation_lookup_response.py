from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.application.enums.operation_lookup_outcome import (
    OperationLookupOutcome,
)


class InProgressOperationLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal[OperationLookupOutcome.IN_PROGRESS]
    operation_id: str = Field(alias="operationId")
