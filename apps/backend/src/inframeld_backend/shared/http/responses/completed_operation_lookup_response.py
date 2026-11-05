from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from inframeld_backend.shared.application.enums.operation_lookup_outcome import (
    OperationLookupOutcome,
)
from inframeld_backend.shared.application.enums.operation_replay_kind import OperationReplayKind


class CompletedOperationLookupResponse(BaseModel):
    """Expose safe synchronous outcome metadata without replaying content."""

    model_config = ConfigDict(extra="forbid")
    outcome: Literal[OperationLookupOutcome.COMPLETED_SYNCHRONOUS]
    operation_id: str = Field(alias="operationId")
    classification: Literal[
        OperationReplayKind.SAFE_RESULT,
        OperationReplayKind.ISSUED_SECRET,
        OperationReplayKind.ANSWER_RECEIPT,
    ]
    idempotency_expires_at: datetime = Field(alias="idempotencyExpiresAt")
