from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ModelConnectionGrantTargetResponse(BaseModel):
    kind: Literal["model-connection"]
    model_connection_id: UUID = Field(serialization_alias="modelConnectionId")
