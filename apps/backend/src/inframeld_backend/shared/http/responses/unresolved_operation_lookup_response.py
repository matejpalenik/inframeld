from typing import Literal

from pydantic import BaseModel, ConfigDict

from inframeld_backend.shared.application.enums.operation_lookup_outcome import (
    OperationLookupOutcome,
)


class UnresolvedOperationLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal[OperationLookupOutcome.UNRESOLVED]
