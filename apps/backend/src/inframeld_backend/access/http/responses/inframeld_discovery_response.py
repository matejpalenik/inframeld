from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class InframeldDiscoveryResponse(BaseModel):
    """Bind the fixed CLI profile to the persistent public installation identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    installation_id: UUID
    client_id: Literal["inframeld-cli"]
