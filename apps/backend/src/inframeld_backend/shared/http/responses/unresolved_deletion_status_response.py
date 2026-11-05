from typing import Literal

from pydantic import BaseModel, ConfigDict

from inframeld_backend.shared.http.enums.deletion_status_outcome import DeletionStatusOutcome


class UnresolvedDeletionStatusResponse(BaseModel):
    """Report no authoritative permitted observation without echoing hidden history."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal[DeletionStatusOutcome.UNRESOLVED]
