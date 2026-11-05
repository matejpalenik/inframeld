from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.application.enums.operation_lookup_outcome import (
    OperationLookupOutcome,
)
from inframeld_backend.shared.http.enums.operation_recovery_reason import OperationRecoveryReason


class RecoveryRequiredOperationLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal[OperationLookupOutcome.RECOVERY_REQUIRED]
    operation_id: str = Field(alias="operationId")
    reason: Literal[OperationRecoveryReason.ORIGINAL_OUTCOME_REQUIRES_RECOVERY]
