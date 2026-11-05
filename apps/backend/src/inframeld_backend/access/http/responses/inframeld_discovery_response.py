from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from inframeld_backend.access.infrastructure.types.human_oauth_client_name import (
    HumanOAuthClientName,
)


class InframeldDiscoveryResponse(BaseModel):
    """Bind the fixed CLI profile to the persistent public installation identity."""

    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1]
    installation_id: UUID
    client_id: Literal[HumanOAuthClientName.INFRAMELD_CLI]
