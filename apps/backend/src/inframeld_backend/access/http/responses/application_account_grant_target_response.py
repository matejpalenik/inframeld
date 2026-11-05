from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.http.enums.grant_target_kind import GrantTargetKind


class ApplicationAccountGrantTargetResponse(BaseModel):
    kind: Literal[GrantTargetKind.APPLICATION_ACCOUNT]
    project_id: UUID = Field(serialization_alias="projectId")
    application_principal_id: UUID = Field(serialization_alias="applicationPrincipalId")
