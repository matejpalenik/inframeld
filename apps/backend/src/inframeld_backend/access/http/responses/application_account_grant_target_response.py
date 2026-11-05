from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ApplicationAccountGrantTargetResponse(BaseModel):
    kind: Literal["application-account"]
    project_id: UUID = Field(serialization_alias="projectId")
    application_principal_id: UUID = Field(serialization_alias="applicationPrincipalId")
