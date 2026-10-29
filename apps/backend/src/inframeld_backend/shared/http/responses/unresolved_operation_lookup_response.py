from typing import Literal

from pydantic import BaseModel, ConfigDict


class UnresolvedOperationLookupResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["unresolved"]
