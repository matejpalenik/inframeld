"""Parse the supported use-only project grant command."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from inframeld_backend.access.domain.enums.project_action import ProjectAction


class ProjectUseOnlyGrantRequest(BaseModel):
    recipient_principal_id: UUID = Field(alias="recipientPrincipalId")
    action_id: Literal[ProjectAction.CREATE_ACCESS_GROUPS] = Field(alias="actionId")
    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
    )
