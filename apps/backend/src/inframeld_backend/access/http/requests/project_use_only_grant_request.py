"""Parse the supported use-only project grant command."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ProjectUseOnlyGrantRequest(BaseModel):
    recipient_principal_id: UUID = Field(alias="recipientPrincipalId")
    action_id: Literal["create-access-groups"] = Field(alias="actionId")
    expected_access_revision: int = Field(
        alias="expectedAccessRevision",
        strict=True,
        ge=0,
    )
