from typing import Literal

from pydantic import BaseModel, ConfigDict


class UnresolvedDeletionStatusResponse(BaseModel):
    """Report no authoritative permitted observation without echoing hidden history."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["unresolved"]
