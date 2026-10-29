from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecoveryRequiredOperationLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["recovery_required"] = "recovery_required"
    operation_id: str = Field(alias="operationId")
    reason: Literal["original_outcome_requires_recovery"] = "original_outcome_requires_recovery"
